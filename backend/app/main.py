"""API REST de GhostShift (TECH_SPEC §5). El veredicto lo calcula siempre el motor determinista."""
from __future__ import annotations

import json
import os
import shutil
import uuid
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import Body, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from ghostshift_engine import EngineParams, Procedure, ProcedureError, TrackSet, compile_procedure, verify_run
from ghostshift_engine.contracts.tracks import FrameObs
from ghostshift_engine.features import resolve_identities
from pydantic import ValidationError

from . import jobs, samples, video
from .db import Database

SESSION_TTL_H = int(os.getenv("SESSION_TTL_HOURS", "24"))
MAX_UPLOAD = video.MAX_BYTES


def load_dotenv() -> None:
    """Lee KEY=VALUE de .env (raíz del repo o backend/) sin pisar variables ya definidas."""
    for d in (Path.cwd(), Path(__file__).resolve().parents[1], Path(__file__).resolve().parents[2]):
        f = d / ".env"
        if f.is_file():
            for line in f.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_app(db_path: str = ":memory:", data_dir: str | None = None, start_jobs: bool = True) -> FastAPI:
    app = FastAPI(title="GhostShift")
    app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                       allow_methods=["*"], allow_headers=["*"])
    db = Database(db_path)
    app.state.db = db
    root = Path(data_dir or os.getenv("GHOSTSHIFT_DATA", "data")).resolve()

    def sdir(sid: str) -> Path:
        d = root / sid
        d.mkdir(parents=True, exist_ok=True)
        return d

    def session_of(pid: str) -> str:
        return procedure_or_404(pid)["session_id"]

    async def save_upload(up: UploadFile, dest: Path) -> Path:
        size = 0
        with dest.open("wb") as f:
            while chunk := await up.read(1 << 20):
                size += len(chunk)
                if size > MAX_UPLOAD:
                    f.close()
                    dest.unlink(missing_ok=True)
                    raise HTTPException(413, "El video pesa más de 200 MB. Recórtalo o comprímelo.")
                f.write(chunk)
        if size == 0:
            raise HTTPException(400, "El archivo está vacío.")
        return dest

    def submit(fn, *args):
        if start_jobs:
            jobs.POOL.submit(fn, *args)

    def session_or_404(sid: str):
        if not db.one("SELECT 1 FROM sessions WHERE id=?", sid):
            raise HTTPException(404, "Sesión no encontrada")

    def procedure_or_404(pid: str):
        row = db.one("SELECT * FROM procedures WHERE id=?", pid)
        if not row:
            raise HTTPException(404, "Procedimiento no encontrado")
        return row

    def latest(pid: str, status: str | None = None):
        sql = "SELECT * FROM procedure_versions WHERE procedure_id=?"
        args: list = [pid]
        if status:
            sql += " AND status=?"
            args.append(status)
        return db.one(sql + " ORDER BY version DESC LIMIT 1", *args)

    @app.post("/sessions", status_code=201)
    def create_session(body: dict = Body(...)):
        if body.get("consent") is not True:
            raise HTTPException(400, "Se requiere consentimiento explícito para enviar vídeos a un proveedor de inferencia")
        sid = str(uuid.uuid4())
        exp = (datetime.now(timezone.utc) + timedelta(hours=SESSION_TTL_H)).isoformat()
        with db.tx() as c:
            c.execute("INSERT INTO sessions VALUES(?,?,?,?)", (sid, now(), exp, now()))
        return {"session_id": sid, "expires_at": exp}

    @app.delete("/sessions/{sid}", status_code=204)
    def delete_session(sid: str):
        session_or_404(sid)
        with db.tx() as c:
            pids = [r["id"] for r in c.execute("SELECT id FROM procedures WHERE session_id=?", (sid,))]
            for pid in pids:
                c.execute("DELETE FROM analyses WHERE procedure_id=?", (pid,))
                c.execute("DELETE FROM runs WHERE procedure_id=?", (pid,))
                c.execute("DELETE FROM procedure_versions WHERE procedure_id=?", (pid,))
            c.execute("DELETE FROM procedures WHERE session_id=?", (sid,))
            c.execute("DELETE FROM model_calls WHERE session_id=?", (sid,))
            c.execute("DELETE FROM sessions WHERE id=?", (sid,))
        shutil.rmtree(root / sid, ignore_errors=True)

    @app.post("/sessions/{sid}/procedures", status_code=201)
    def create_procedure(sid: str, name: str = Body(...), draft: dict = Body(...)):
        session_or_404(sid)
        proc = _parse(draft)
        pid = str(uuid.uuid4())
        proc.procedure_id, proc.version, proc.approved_by_user = pid, 1, False
        with db.tx() as c:
            c.execute("INSERT INTO procedures VALUES(?,?,?,?)", (pid, sid, name, now()))
            _save(c, proc, "draft")
        return {"procedure_id": pid, "version": 1, "status": "draft"}

    @app.put("/procedures/{pid}/rules")
    def edit_rules(pid: str, draft: dict = Body(..., embed=True)):
        """Guarda ediciones. Si la última versión está aprobada, crea una nueva versión borrador."""
        procedure_or_404(pid)
        last = latest(pid)
        proc = _parse(draft)
        proc.procedure_id, proc.approved_by_user = pid, False
        proc.version = last["version"] + (1 if last["status"] == "approved" else 0)
        proc.parent_version = last["version"] if last["status"] == "approved" else None
        with db.tx() as c:
            if last["status"] == "draft":
                c.execute("DELETE FROM procedure_versions WHERE procedure_id=? AND version=?", (pid, proc.version))
            _save(c, proc, "draft")
        return {"procedure_id": pid, "version": proc.version, "status": "draft"}

    @app.post("/procedures/{pid}/approve")
    def approve(pid: str):
        procedure_or_404(pid)
        last = latest(pid)
        if last["status"] == "approved":
            raise HTTPException(409, "La última versión ya está aprobada")
        proc = Procedure.model_validate_json(last["content_json"])
        proc.approved_by_user = True
        try:
            compiled = compile_procedure(proc)
        except ProcedureError as e:
            raise HTTPException(422, str(e)) from e
        with db.tx() as c:
            c.execute("DELETE FROM procedure_versions WHERE procedure_id=? AND version=?", (pid, proc.version))
            _save(c, proc, "approved", compiled.content_hash)
        return {"procedure_id": pid, "version": proc.version, "status": "approved",
                "content_hash": compiled.content_hash}

    @app.post("/procedures/{pid}/runs/from-tracks", status_code=201)
    def run_from_tracks(pid: str, tracks: dict = Body(...)):
        """Ejecuta el verificador sobre pistas ya calculadas (evaluación y reproducción; no llama a modelos)."""
        procedure_or_404(pid)
        approved = latest(pid, "approved")
        if not approved:
            raise HTTPException(409, "No hay una versión aprobada; no se puede verificar con borradores")
        try:
            ts = TrackSet.model_validate(tracks)
        except ValidationError as e:
            raise HTTPException(422, e.errors(include_url=False, include_input=False)) from e
        compiled = compile_procedure(Procedure.model_validate_json(approved["content_json"]))
        report = verify_run(compiled, ts)
        rid = str(uuid.uuid4())
        with db.tx() as c:
            c.execute("INSERT INTO runs(id,procedure_id,procedure_version,status,verdict,report_json,created_at,"
                      "stages_json,tracks_json) VALUES(?,?,?,?,?,?,?,?,?)",
                      (rid, pid, approved["version"], "done", report.verdict.value,
                       json.dumps(asdict(report)), now(), "[]", ts.model_dump_json()))
        return {"run_id": rid, "verdict": report.verdict.value}

    # --- vistas, subidas y trabajos (frontend) ---
    def _meta(row) -> dict:
        return json.loads(row["meta_json"]) if row and row["meta_json"] else {}

    def _proc_status(pid: str, an) -> str:
        if an and an["status"] in ("queued", "running"):
            return "analyzing"
        if an and an["status"] == "failed":
            return "failed"
        last = latest(pid)
        if not last:
            return "analyzing"
        return "approved" if last["status"] == "approved" else "ready"

    @app.get("/samples")
    def list_samples():
        return [{"id": x["id"], "kind": x["kind"], "title_es": x["title_es"], "description_es": x["description_es"],
                 "expected": x["expected"], "video_url": f"/samples/{x['id']}/video"} for x in samples.SAMPLES]

    @app.get("/samples/{sample_id}/video")
    def sample_video(sample_id: str):
        if sample_id not in samples.BY_ID:
            raise HTTPException(404, "Ejemplo no encontrado")
        return FileResponse(samples.path(sample_id), media_type="video/mp4")

    @app.get("/sessions/{sid}/procedures")
    def list_procedures(sid: str):
        session_or_404(sid)
        out = []
        for p in db.all("SELECT * FROM procedures WHERE session_id=? ORDER BY created_at DESC", sid):
            an = db.one("SELECT status FROM analyses WHERE procedure_id=?", p["id"])
            last = latest(p["id"])
            n = len(json.loads(last["content_json"])["rules"]) if last else 0
            out.append({"procedure_id": p["id"], "name": p["name"], "status": _proc_status(p["id"], an),
                        "version": last["version"] if last else 0, "created_at": p["created_at"], "n_rules": n})
        return out

    def _start_analysis(sid: str, name: str, src: Path):
        pid = str(uuid.uuid4())
        with db.tx() as c:
            c.execute("INSERT INTO procedures VALUES(?,?,?,?)", (pid, sid, name.strip() or "Procedimiento", now()))
            c.execute("INSERT INTO analyses(procedure_id,status,stages_json,source_path) VALUES(?,?,?,?)",
                      (pid, "queued", jobs.fresh_stages(jobs.ANALYSIS_STAGES), str(src)))
        submit(jobs.run_analysis, db, pid, sid, sdir(sid))
        return pid

    @app.post("/sessions/{sid}/procedures/from-video", status_code=202)
    async def procedure_from_video(sid: str, name: str = Form(...), video_file: UploadFile = File(..., alias="video")):
        session_or_404(sid)
        src = await save_upload(video_file, sdir(sid) / f"ref_src_{uuid.uuid4().hex}")
        return {"procedure_id": _start_analysis(sid, name, src)}

    @app.post("/sessions/{sid}/procedures/from-sample", status_code=202)
    def procedure_from_sample(sid: str, body: dict = Body(...)):
        session_or_404(sid)
        sample = samples.BY_ID.get(body.get("sample_id"))
        if not sample or sample["kind"] != "reference":
            raise HTTPException(404, "Ejemplo de referencia no encontrado")
        src = sdir(sid) / f"ref_src_{uuid.uuid4().hex}"
        shutil.copyfile(samples.path(sample["id"]), src)
        return {"procedure_id": _start_analysis(sid, body.get("name") or sample["title_es"], src)}

    @app.post("/procedures/{pid}/retry", status_code=202)
    def retry_analysis(pid: str):
        sid = session_of(pid)
        an = db.one("SELECT status FROM analyses WHERE procedure_id=?", pid)
        if not an or an["status"] != "failed":
            raise HTTPException(409, "Solo se puede reintentar un análisis fallido")
        with db.tx() as c:
            c.execute("UPDATE analyses SET status='queued', error_json=NULL, stages_json=? WHERE procedure_id=?",
                      (jobs.fresh_stages(jobs.ANALYSIS_STAGES), pid))
        submit(jobs.run_analysis, db, pid, sid, sdir(sid))
        return {"procedure_id": pid}

    @app.get("/procedures/{pid}")
    def get_procedure(pid: str):
        p = procedure_or_404(pid)
        an = db.one("SELECT * FROM analyses WHERE procedure_id=?", pid)
        last = latest(pid)
        meta = _meta(an)
        draft = None
        if last and (not an or an["status"] == "done"):
            content = json.loads(last["content_json"])
            extra = json.loads(an["draft_json"]) if an and an["draft_json"] else {}
            draft = {"version": last["version"], "approved": last["status"] == "approved",
                     "objects": content["objects"], "zones": [{**z, "polygon": [list(v) for v in z["polygon"]]} for z in content["zones"]],
                     "rules": [{k: v for k, v in r.items() if v is not None} for r in content["rules"]],
                     "timeline": extra.get("timeline", []), "uncertainties": extra.get("uncertainties", [])}
        analysis = ({"status": {"queued": "running"}.get(an["status"], an["status"]),
                     "stages": json.loads(an["stages_json"]),
                     "error": json.loads(an["error_json"]) if an["error_json"] else None}
                    if an else {"status": "done", "stages": [], "error": None})
        return {"procedure_id": pid, "name": p["name"], "status": _proc_status(pid, an),
                "version": last["version"] if last else 0, "video_url": f"/procedures/{pid}/video" if an and an["video_path"] else None,
                "duration_ms": meta.get("duration_ms"), "width": meta.get("width"), "height": meta.get("height"),
                "analysis": analysis, "draft": draft}

    @app.get("/procedures/{pid}/video")
    def procedure_video(pid: str):
        procedure_or_404(pid)
        an = db.one("SELECT video_path FROM analyses WHERE procedure_id=?", pid)
        if not an or not an["video_path"] or not Path(an["video_path"]).is_file():
            raise HTTPException(404, "El video aún no está disponible")
        return FileResponse(an["video_path"], media_type="video/mp4")

    def _start_run(pid: str, src: Path) -> str:
        approved = latest(pid, "approved")
        if not approved:
            raise HTTPException(409, "No hay una versión aprobada; no se puede verificar con borradores")
        rid = str(uuid.uuid4())
        with db.tx() as c:
            c.execute("INSERT INTO runs(id,procedure_id,procedure_version,status,created_at,source_path,stages_json)"
                      " VALUES(?,?,?,?,?,?,?)", (rid, pid, approved["version"], "queued", now(), str(src),
                                                 jobs.fresh_stages(jobs.RUN_STAGES)))
        submit(jobs.run_verification, db, rid, session_of(pid), sdir(session_of(pid)))
        return rid

    @app.post("/procedures/{pid}/runs/from-video", status_code=202)
    async def run_from_video(pid: str, video_file: UploadFile = File(..., alias="video")):
        sid = session_of(pid)
        if not latest(pid, "approved"):
            raise HTTPException(409, "No hay una versión aprobada; no se puede verificar con borradores")
        src = await save_upload(video_file, sdir(sid) / f"run_src_{uuid.uuid4().hex}")
        return {"run_id": _start_run(pid, src)}

    @app.post("/procedures/{pid}/runs/from-sample", status_code=202)
    def run_from_sample(pid: str, body: dict = Body(...)):
        sid = session_of(pid)
        sample = samples.BY_ID.get(body.get("sample_id"))
        if not sample or sample["kind"] != "run":
            raise HTTPException(404, "Ejemplo de ejecución no encontrado")
        if not latest(pid, "approved"):
            raise HTTPException(409, "No hay una versión aprobada; no se puede verificar con borradores")
        src = sdir(sid) / f"run_src_{uuid.uuid4().hex}"
        shutil.copyfile(samples.path(sample["id"]), src)
        return {"run_id": _start_run(pid, src)}

    @app.get("/procedures/{pid}/runs")
    def list_runs(pid: str):
        procedure_or_404(pid)
        return [{"run_id": r["id"], "status": r["status"], "verdict": r["verdict"], "created_at": r["created_at"]}
                for r in db.all("SELECT * FROM runs WHERE procedure_id=? ORDER BY created_at DESC", pid)]

    def run_or_404(rid: str):
        row = db.one("SELECT * FROM runs WHERE id=?", rid)
        if not row:
            raise HTTPException(404, "Ejecución no encontrada")
        return row

    @app.get("/runs/{rid}")
    def get_run(rid: str):
        row = run_or_404(rid)
        meta = _meta(row)
        report = jobs.report_view(rid, json.loads(row["report_json"]), meta.get("camera")) if row["report_json"] else None
        return {"run_id": rid, "procedure_id": row["procedure_id"], "procedure_version": row["procedure_version"],
                "status": {"queued": "running"}.get(row["status"], row["status"]),
                "stages": json.loads(row["stages_json"] or "[]"),
                "error": json.loads(row["error_json"]) if row["error_json"] else None,
                "video_url": f"/runs/{rid}/video" if row["video_path"] else None,
                "duration_ms": meta.get("duration_ms"), "report": report}

    @app.post("/runs/{rid}/retry", status_code=202)
    def retry_run(rid: str):
        row = run_or_404(rid)
        if row["status"] != "failed":
            raise HTTPException(409, "Solo se puede reintentar una verificación fallida")
        with db.tx() as c:
            c.execute("UPDATE runs SET status='queued', error_json=NULL, stages_json=? WHERE id=?",
                      (jobs.fresh_stages(jobs.RUN_STAGES), rid))
        submit(jobs.run_verification, db, rid, session_of(row["procedure_id"]), sdir(session_of(row["procedure_id"])))
        return {"run_id": rid}

    @app.get("/runs/{rid}/video")
    def run_video(rid: str):
        row = run_or_404(rid)
        if not row["video_path"] or not Path(row["video_path"]).is_file():
            raise HTTPException(404, "El video aún no está disponible")
        return FileResponse(row["video_path"], media_type="video/mp4")

    @app.get("/runs/{rid}/frames/{t_ms}.jpg")
    def run_frame(rid: str, t_ms: int, obj: str | None = None):
        row = run_or_404(rid)
        if not row["video_path"] or not row["tracks_json"]:
            raise HTTPException(404, "Aún no hay fotogramas")
        ts = TrackSet.model_validate_json(row["tracks_json"])
        box = None
        if obj:
            f = min(range(len(ts.clip.frame_t_ms)), key=lambda i: abs(ts.clip.frame_t_ms[i] - t_ms))
            # misma resolución de identidad que el motor (un prompt puede devolver varias instancias)
            ids = sorted({tl.prompt_id[4:] for tl in ts.tracklets if tl.prompt_id.startswith("obj:")})
            chosen, _ = resolve_identities(ts, ids, EngineParams())
            near = [chosen.get(obj, {}).get(g) for g in (f, f - 1, f + 1)]
            obs = [o for o in near if isinstance(o, FrameObs)]
            if obs:
                box = obs[0].bbox
        try:
            jpg = video.evidence_frame(Path(row["video_path"]), t_ms, box, ts.clip.width, ts.clip.height)
        except video.VideoError as e:
            raise HTTPException(500, str(e)) from e
        return Response(jpg, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=3600"})


    @app.get("/audit/{sid}")
    def audit(sid: str):
        session_or_404(sid)
        return [dict(r) for r in db.all("SELECT * FROM model_calls WHERE session_id=? ORDER BY id", sid)]

    def _parse(draft: dict) -> Procedure:
        try:
            return Procedure.model_validate({**draft, "procedure_id": "tmp"})
        except ValidationError as e:
            raise HTTPException(422, e.errors(include_url=False, include_input=False)) from e

    def _save(c, proc: Procedure, status: str, chash: str | None = None):
        c.execute("INSERT INTO procedure_versions VALUES(?,?,?,?,?,?)",
                  (proc.procedure_id, proc.version, status, proc.model_dump_json(by_alias=True),
                   chash or proc.content_hash(), now()))

    return app


load_dotenv()
app = create_app(os.getenv("GHOSTSHIFT_DB", "data/ghostshift.db"))
