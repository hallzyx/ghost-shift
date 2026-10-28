"""API REST de GhostShift (TECH_SPEC §5). El veredicto lo calcula siempre el motor determinista."""
from __future__ import annotations

import json
import os
import uuid
from dataclasses import asdict
from datetime import datetime, timedelta, timezone

from fastapi import Body, FastAPI, HTTPException
from ghostshift_engine import Procedure, ProcedureError, TrackSet, compile_procedure, verify_run
from pydantic import ValidationError

from .db import Database

SESSION_TTL_H = int(os.getenv("SESSION_TTL_HOURS", "24"))


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_app(db_path: str = ":memory:") -> FastAPI:
    app = FastAPI(title="GhostShift")
    db = Database(db_path)

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
                c.execute("DELETE FROM runs WHERE procedure_id=?", (pid,))
                c.execute("DELETE FROM procedure_versions WHERE procedure_id=?", (pid,))
            c.execute("DELETE FROM procedures WHERE session_id=?", (sid,))
            c.execute("DELETE FROM model_calls WHERE session_id=?", (sid,))
            c.execute("DELETE FROM sessions WHERE id=?", (sid,))

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
            c.execute("INSERT INTO runs VALUES(?,?,?,?,?,?,?)",
                      (rid, pid, approved["version"], "done", report.verdict.value,
                       json.dumps(asdict(report)), now()))
        return {"run_id": rid, "verdict": report.verdict.value}

    @app.get("/runs/{rid}")
    def get_run(rid: str):
        row = db.one("SELECT * FROM runs WHERE id=?", rid)
        if not row:
            raise HTTPException(404, "Ejecución no encontrada")
        return {"run_id": rid, "procedure_version": row["procedure_version"], "report": json.loads(row["report_json"])}

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


app = create_app(os.getenv("GHOSTSHIFT_DB", ":memory:"))
