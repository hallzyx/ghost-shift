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

from . import camera, video
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
        job.audit("sam", {"model": "sam-3.1", "request_id": res.request_id}, int((time.time() - t0) * 1000),
                  "cached" if res.cached else "ok")
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
        job.audit("muse", info, int((time.time() - t0) * 1000), info.get("status", "ok"))
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
        job.stage("segment", "done", ", ".join(_seg_detail(results, "obj:" + o["id"], o["id"]) for o in objects))

        stage = "propose"
        job.stage("propose", "running")
        cam = _camera_reference(norm, ts, dest / f"ref_anchor_{pid}.png")
        meta["camera"] = cam.info
        job.set(meta_json=json.dumps(meta))
        draft = propose_draft(cam.tracks, objects, proposal)
        draft["uncertainties"] += camera_uncertainties(cam.info)
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


def _seg_detail(results, prompt_id: str, oid: str) -> str:
    frames = {d.frame for r in results if r.prompt_id == prompt_id for d in r.detections}
    inst = {d.object_id for r in results if r.prompt_id == prompt_id for d in r.detections}
    return f"{oid}: {len(frames)} fotogramas" + (f" ({len(inst)} instancias)" if len(inst) > 1 else "")


def _safe_register(norm: Path, ts: TrackSet, ref_anchor=None, ref_boxes=None):
    """Registro de cámara; cualquier fallo de OpenCV se trata como «no comprobado», nunca como alineado."""
    try:
        frames = camera.read_frames(norm)
        reg = camera.register_clip(frames, ts)
        cross, n_in = (None, 0)
        if ref_anchor is not None and reg.status in ("static", "compensated"):
            cross, n_in = camera.register_cross(frames, reg, ts, ref_anchor, ref_boxes or [])
        return frames, reg, cross, n_in
    except Exception as e:  # noqa: BLE001
        reg = camera.ClipRegistration("unchecked", len(ts.clip.frame_t_ms) - 1, [], 0.0, 0.0, 0, error=str(e)[:200])
        return [], reg, None, 0


def _camera_reference(norm: Path, ts: TrackSet, anchor_path: Path) -> camera.CameraOutcome:
    frames, reg, _, _ = _safe_register(norm, ts)
    out = camera.calibrate(reg, None, 0, False, ts)
    if frames and reg.status in ("static", "compensated"):
        camera.save_anchor(frames, reg, anchor_path)
        out.info["anchor_path"] = str(anchor_path)
        out.info["anchor_boxes"] = [list(o.bbox) for tl in ts.tracklets for o in tl.obs if o.f == reg.anchor]
        out.info["anchor_t_ms"] = ts.clip.frame_t_ms[reg.anchor]
    return out


def _camera_run(norm: Path, ts: TrackSet, ref_cam: dict | None) -> camera.CameraOutcome:
    anchor = camera.load_anchor(Path(ref_cam["anchor_path"])) if ref_cam and ref_cam.get("anchor_path") else None
    _, reg, cross, n_in = _safe_register(norm, ts, anchor, (ref_cam or {}).get("anchor_boxes"))
    return camera.calibrate(reg, cross, n_in, anchor is not None, ts)


def camera_uncertainties(info: dict) -> list[str]:
    st = info.get("status")
    if st == "unstable":
        return [f"La cámara se mueve demasiado en la referencia (solo {info['registered_ratio']:.0%} de los fotogramas se "
                "pudieron alinear con la mesa): las zonas propuestas no son fiables. Graba con la cámara apoyada."]
    if st == "compensated":
        return [f"Cámara en mano: el encuadre se desplaza hasta un {info['max_shift']:.0%} de la diagonal. GhostShift lo "
                f"compensa con la textura de la mesa y las zonas se refieren al fotograma de {info.get('anchor_t_ms', 0) / 1000:.1f} s."]
    return []


CAMERA_ES = {
    "ALIGNED": "Cámara fija: el encuadre coincide con el de la referencia.",
    "RECALIBRATED": "La cámara se movió; se compensó con la textura de la mesa y las zonas siguen a la mesa.",
    "UNCHECKED": "No se pudo comprobar la estabilidad de la cámara (fondo sin textura): se asume fija.",
    "INCOMPATIBLE": "La cámara se movió demasiado o no se pudo alinear: no se decide nada sobre posiciones.",
}


def camera_view(status: str, info: dict | None) -> dict:
    """Aviso de cámara para el UI: estado del motor + números del registro."""
    info = info or {}
    moved = bool(info.get("moved_vs_reference"))
    msg = CAMERA_ES.get(status, status)
    if status == "INCOMPATIBLE" and info.get("status") == "unstable":
        msg = (f"La cámara se movió demasiado: solo {info.get('registered_ratio', 0):.0%} de los fotogramas se pudieron "
               "alinear con la mesa. No se decide nada; repite la grabación con la cámara apoyada.")
    if moved:
        msg = "No se pudo alinear este video con el de la referencia: las reglas de zona quedan en revisión."
    return {"status": status, "message_es": msg, "aligned_to_reference": not moved,
            "max_shift": info.get("max_shift"), "registered_ratio": info.get("registered_ratio"),
            "reference_shift": info.get("cross_shift"), "warning": status in ("RECALIBRATED", "INCOMPATIBLE", "UNCHECKED") or bool(moved)}


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
        job.stage("segment", "done", ", ".join(_seg_detail(results, "obj:" + o["id"], o["id"]) for o in objs))

        stage = "verify"
        job.stage("verify", "running")
        ref = db.one("SELECT meta_json FROM analyses WHERE procedure_id=?", run["procedure_id"])
        ref_cam = (json.loads(ref["meta_json"]) if ref and ref["meta_json"] else {}).get("camera")
        cam = _camera_run(norm, ts, ref_cam)
        meta["camera"] = cam.info
        report = verify_run(compile_procedure(proc), cam.tracks, cam.calibration)
        # tracks_json guarda las cajas ORIGINALES (para dibujar la evidencia sobre el video de la ejecución)
        job.set(report_json=json.dumps(asdict(report)), verdict=report.verdict.value, meta_json=json.dumps(meta),
                tracks_json=ts.model_dump_json(), status="done")
        job.stage("verify", "done", report.verdict.value)
    except video.VideoError as e:
        job.fail(stage, str(e), False)
    except ModelCallError as e:
        job.fail(stage, str(e), e.retryable)
    except Exception as e:  # noqa: BLE001
        job.fail(stage, f"Error inesperado en la verificación: {e}", True)


def report_view(rid: str, report: dict, camera_info: dict | None = None) -> dict:
    """Informe del motor -> contrato del frontend (añade explicación en español y URLs de evidencia)."""
    rules = []
    for r in report["rules"]:
        ev = [{**e, "frame_url": f"/runs/{rid}/frames/{e['t_ms']}.jpg?obj={e['obj']}"} for e in r["evidence"]]
        rules.append({"rule_id": r["rule_id"], "text_es": r["text_es"], "verdict": r["verdict"], "reason": r["reason"],
                      "reason_es": reason_es(r["reason"]), "evidence": ev, "missing": r["missing"]})
    return {"verdict": report["verdict"], "camera_status": report["camera_status"],
            "camera": camera_view(report["camera_status"], camera_info),
            "blocking_issues": report["blocking_issues"], "rules": rules,
            "events": [{"kind": e["kind"], "obj": e["obj"], "zone": e["zone"], "t_lo": e["t_lo"], "t_hi": e["t_hi"],
                        "timing_uncertain": e["timing_uncertain"]} for e in report["events"]]}
