"""Trabajos en segundo plano: análisis de la referencia y verificación de ejecuciones."""
from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from ghostshift_engine import Procedure, TrackSet, compile_procedure, verify_run
from ghostshift_engine.contracts.tracks import AbsenceProbe

from . import video
from .db import Database
from .meta import muse_client, sam_client
from .meta.sam_adapter import ModelCallError, build_trackset
from .pipeline.propose import propose_draft
from .pipeline.reasons import reason_es

POOL = ThreadPoolExecutor(max_workers=4)
ANALYSIS_STAGES = [("validate", "Validando el video"), ("interpret", "Muse Spark interpreta la escena"),
                   ("segment", "SAM 3.1 sigue cada objeto"), ("propose", "Preparando las reglas propuestas")]
RUN_STAGES = [("validate", "Validando el video"), ("segment", "SAM 3.1 sigue cada objeto"),
              ("verify", "El motor comprueba las reglas")]


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def fresh_stages(spec) -> str:
    return json.dumps([{"id": i, "label": label, "state": "pending", "detail": None} for i, label in spec])


class Job:
    """Acceso a una fila (analyses/runs) con helpers de etapas y errores."""

    def __init__(self, db: Database, table: str, key: str, row_id: str, session_id: str):
        self.db, self.table, self.key, self.id, self.sid = db, table, key, row_id, session_id

    def stage(self, sid: str, state: str, detail: str | None = None):
        row = self.db.one(f"SELECT stages_json FROM {self.table} WHERE {self.key}=?", self.id)
        stages = json.loads(row["stages_json"])
        for s in stages:
            if s["id"] == sid:
                s["state"], s["detail"] = state, detail
        with self.db.tx() as c:
            c.execute(f"UPDATE {self.table} SET stages_json=? WHERE {self.key}=?", (json.dumps(stages), self.id))

    def fail(self, stage: str | None, message: str, retryable: bool):
        if stage:
            self.stage(stage, "failed", message)
        with self.db.tx() as c:
            c.execute(f"UPDATE {self.table} SET status='failed', error_json=? WHERE {self.key}=?",
                      (json.dumps({"message": message, "retryable": retryable}), self.id))

    def set(self, **cols):
        sets = ", ".join(f"{k}=?" for k in cols)
        with self.db.tx() as c:
            c.execute(f"UPDATE {self.table} SET {sets} WHERE {self.key}=?", (*cols.values(), self.id))

    def audit(self, kind: str, info: dict, latency_ms: int, status: str = "ok", error: str | None = None):
        with self.db.tx() as c:
            c.execute("INSERT INTO model_calls(session_id,kind,model_version,request_id,latency_ms,status,error,created_at)"
                      " VALUES(?,?,?,?,?,?,?,?)",
                      (self.sid, kind, info.get("model"), info.get("request_id"), latency_ms, status, error, now()))


def _segment_all(job: Job, data: bytes, prompts: list[tuple[str, str]], meta: dict):
    """Una petición SAM por concepto, en paralelo. `prompts`: [(prompt_id, texto)]."""
    def one(item):
        pid, text = item
        t0 = time.time()
        try:
            res = sam_client.segment(data, text, pid)
        except ModelCallError as e:
            job.audit("sam", {"model": "sam-3.1"}, int((time.time() - t0) * 1000), "error", str(e))
            raise
        job.audit("sam", {"model": "sam-3.1", "request_id": res.request_id}, int((time.time() - t0) * 1000))
        return res
    with ThreadPoolExecutor(max_workers=len(prompts)) as ex:
        return list(ex.map(one, prompts))


def run_analysis(db: Database, pid: str, session_id: str, dest: Path):
    job = Job(db, "analyses", "procedure_id", pid, session_id)
    stage = "validate"
    try:
        row = db.one("SELECT source_path FROM analyses WHERE procedure_id=?", pid)
        job.set(status="running", error_json=None, stages_json=fresh_stages(ANALYSIS_STAGES))
        job.stage("validate", "running")
        norm = dest / "reference.mp4"
        meta = video.normalize(Path(row["source_path"]), norm)
        job.set(video_path=str(norm), meta_json=json.dumps(meta))
        job.stage("validate", "done", f"{meta['duration_ms'] / 1000:.1f} s · {meta['width']}×{meta['height']}")
        data = norm.read_bytes()

        stage = "interpret"
        job.stage("interpret", "running")
        t0 = time.time()
        try:
            proposal, info = muse_client.propose(data)
        except ModelCallError as e:
            job.audit("muse", {"model": muse_client.MODEL}, int((time.time() - t0) * 1000), "error", str(e))
            raise
        job.audit("muse", info, int((time.time() - t0) * 1000))
        objects = []
        for i, o in enumerate(proposal.get("objects", [])[:4]):
            objects.append({"id": chr(65 + i), "label_es": o["label_es"].strip().capitalize(),
                            "sam_prompt": o["sam_prompt"].strip().lower()})
        if not objects:
            raise ValueError("Muse Spark no encontró objetos en el video. Comprueba que la mesa y los objetos se vean bien.")
        # Muse usa sus propios ids; se remapean a A, B, C… por orden
        remap = {o["id"]: chr(65 + i) for i, o in enumerate(proposal["objects"][:4])}
        proposal["events"] = [{**e, "object": remap[e["object"]]} for e in proposal.get("events", []) if e["object"] in remap]
        job.stage("interpret", "done", f"{len(objects)} objetos propuestos")

        stage = "segment"
        job.stage("segment", "running")
        results = _segment_all(job, data, [(f"obj:{o['id']}", o["sam_prompt"]) for o in objects] + [("aux:hand", "hand")], meta)
        ts = build_trackset(pid, "", meta, results)
        job.stage("segment", "done", ", ".join(f"{o['id']}: {sum(len(r.detections) for r in results if r.prompt_id == 'obj:' + o['id'])} fotogramas" for o in objects))

        stage = "propose"
        job.stage("propose", "running")
        draft = propose_draft(ts, objects, proposal)
        proc = Procedure.model_validate({"procedure_id": pid, "version": 1, "approved_by_user": False,
                                         **{k: draft[k] for k in ("objects", "zones", "rules")}})
        with db.tx() as c:
            c.execute("DELETE FROM procedure_versions WHERE procedure_id=? AND version=1 AND status='draft'", (pid,))
            c.execute("INSERT INTO procedure_versions VALUES(?,?,?,?,?,?)",
                      (pid, 1, "draft", proc.model_dump_json(by_alias=True), proc.content_hash(), now()))
        job.set(draft_json=json.dumps(draft), tracks_json=ts.model_dump_json(), status="done")
        job.stage("propose", "done", f"{len(draft['rules'])} reglas propuestas")
    except video.VideoError as e:
        job.fail(stage, str(e), False)
    except ModelCallError as e:
        job.fail(stage, str(e), e.retryable)
    except Exception as e:  # noqa: BLE001 - el usuario debe ver un error accionable, no un 500
        job.fail(stage, f"Error inesperado en el análisis: {e}", True)


def _probes(ts: TrackSet, objects: list[dict]) -> list[AbsenceProbe]:
    """Sondeo de ausencia solo para objetos que no se detectaron NUNCA en el clip (ausencia, no oclusión)."""
    n = len(ts.clip.frame_t_ms)
    out = []
    for o in objects:
        pid = f"obj:{o['id']}"
        if not any(tl.obs for tl in ts.tracklets if tl.prompt_id == pid):
            out.append(AbsenceProbe(prompt_id=pid, frames=list(range(max(0, n - 5), n)), max_score=0.0))
    return out


def run_verification(db: Database, rid: str, session_id: str, dest: Path):
    job = Job(db, "runs", "id", rid, session_id)
    stage = "validate"
    try:
        run = db.one("SELECT * FROM runs WHERE id=?", rid)
        ver = db.one("SELECT content_json FROM procedure_versions WHERE procedure_id=? AND version=?",
                     run["procedure_id"], run["procedure_version"])
        proc = Procedure.model_validate_json(ver["content_json"])
        job.set(status="running", error_json=None, stages_json=fresh_stages(RUN_STAGES))
        job.stage("validate", "running")
        norm = dest / f"run_{rid}.mp4"
        meta = video.normalize(Path(run["source_path"]), norm)
        job.set(video_path=str(norm), meta_json=json.dumps(meta))
        job.stage("validate", "done", f"{meta['duration_ms'] / 1000:.1f} s · {meta['width']}×{meta['height']}")
        data = norm.read_bytes()

        stage = "segment"
        job.stage("segment", "running")
        objs = [{"id": o.id, "prompt": o.sam_prompt or o.description} for o in proc.objects]
        results = _segment_all(job, data, [(f"obj:{o['id']}", o["prompt"]) for o in objs] + [("aux:hand", "hand")], meta)
        ts = build_trackset(rid, "", meta, results)
        ts.absence_probes = _probes(ts, objs)
        job.stage("segment", "done")

        stage = "verify"
        job.stage("verify", "running")
        report = verify_run(compile_procedure(proc), ts)
        job.set(report_json=json.dumps(asdict(report)), verdict=report.verdict.value,
                tracks_json=ts.model_dump_json(), status="done")
        job.stage("verify", "done", report.verdict.value)
    except video.VideoError as e:
        job.fail(stage, str(e), False)
    except ModelCallError as e:
        job.fail(stage, str(e), e.retryable)
    except Exception as e:  # noqa: BLE001
        job.fail(stage, f"Error inesperado en la verificación: {e}", True)


def report_view(rid: str, report: dict) -> dict:
    """Informe del motor -> contrato del frontend (añade explicación en español y URLs de evidencia)."""
    rules = []
    for r in report["rules"]:
        ev = [{**e, "frame_url": f"/runs/{rid}/frames/{e['t_ms']}.jpg?obj={e['obj']}"} for e in r["evidence"]]
        rules.append({"rule_id": r["rule_id"], "text_es": r["text_es"], "verdict": r["verdict"], "reason": r["reason"],
                      "reason_es": reason_es(r["reason"]), "evidence": ev, "missing": r["missing"]})
    return {"verdict": report["verdict"], "camera_status": report["camera_status"],
            "blocking_issues": report["blocking_issues"], "rules": rules,
            "events": [{"kind": e["kind"], "obj": e["obj"], "zone": e["zone"], "t_lo": e["t_lo"], "t_hi": e["t_hi"],
                        "timing_uncertain": e["timing_uncertain"]} for e in report["events"]]}
