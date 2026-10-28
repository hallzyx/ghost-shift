"""Flujo completo (análisis -> aprobación -> verificación) con respuestas de modelos grabadas."""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import jobs, main
from app.meta import muse_client, sam_client
from app.meta.sam_adapter import ModelCallError, SamResult, parse_deltas

FIX = Path(__file__).parent / "fixtures" / "sam"
MUSE = {"objects": [{"id": "A", "label_es": "cuadrado azul", "sam_prompt": "blue square"},
                    {"id": "B", "label_es": "cuadrado amarillo", "sam_prompt": "yellow square"}],
        "zones": [], "events": [{"type": "place", "object": "A", "zone_label_es": "izq", "t_seconds": 2.1},
                                {"type": "place", "object": "B", "zone_label_es": "der", "t_seconds": 5.2}],
        "uncertainties": ["Dudas de ejemplo."]}
FIXTURE_FOR = {"blue square": "blue_conf", "yellow square": "yellow_conf", "hand": "hand_conf"}


def fake_segment(video, prompt, prompt_id, **kw):
    d = json.loads((FIX / f"{FIXTURE_FOR[prompt]}.json").read_text())
    return SamResult(prompt_id, parse_deltas(d["deltas"]), d["video_frames_processed"], "req-test")


@pytest.fixture
def ctx(tmp_path, monkeypatch):
    monkeypatch.setattr(sam_client, "segment", fake_segment)
    monkeypatch.setattr(muse_client, "propose", lambda data: (json.loads(json.dumps(MUSE)), {"request_id": "m1", "model": "muse-spark-1.3"}))
    app = main.create_app(":memory:", str(tmp_path / "data"), start_jobs=False)
    c = TestClient(app)
    sid = c.post("/sessions", json={"consent": True}).json()["session_id"]
    return c, sid, app, tmp_path / "data"


def analyze(c, sid, app, data):
    pid = c.post(f"/sessions/{sid}/procedures/from-sample", json={"name": "Kit", "sample_id": "reference"}).json()["procedure_id"]
    return pid


def test_samples_listed(ctx):
    c, *_ = ctx
    s = c.get("/samples").json()
    assert {x["id"] for x in s} >= {"reference", "run_ok", "run_wrong_order"} and all(x["video_url"] for x in s)


def test_consent_required():
    c = TestClient(main.create_app(start_jobs=False))
    assert c.post("/sessions", json={}).status_code == 400


def test_full_flow(ctx):
    c, sid, app, data = ctx
    pid = analyze(c, sid, app, data)
    v = c.get(f"/procedures/{pid}").json()
    assert v["status"] == "analyzing" and v["analysis"]["status"] == "running" and v["draft"] is None
    jobs.run_analysis(app.state.db, pid, sid, data / sid)
    v = c.get(f"/procedures/{pid}").json()
    assert v["status"] == "ready" and v["analysis"]["status"] == "done"
    assert [s["state"] for s in v["analysis"]["stages"]] == ["done"] * 4
    d = v["draft"]
    assert [o["sam_prompt"] for o in d["objects"]] == ["blue square", "yellow square"]
    assert [r["type"] for r in d["rules"]] == ["in_zone_at", "in_zone_at", "before"]
    assert [(e["object"], e["t_ms"]) for e in d["timeline"]] == [("A", 1800), ("B", 4800)]
    assert d["uncertainties"] == ["Dudas de ejemplo."]
    # no se puede verificar sin aprobar
    assert c.post(f"/procedures/{pid}/runs/from-sample", json={"sample_id": "run_ok"}).status_code == 409
    assert c.put(f"/procedures/{pid}/rules", json={"draft": {k: d[k] for k in ("objects", "zones", "rules")}}).status_code == 200
    assert c.post(f"/procedures/{pid}/approve").json()["status"] == "approved"
    rid = c.post(f"/procedures/{pid}/runs/from-sample", json={"sample_id": "run_ok"}).json()["run_id"]
    assert c.get(f"/runs/{rid}").json()["status"] == "running"
    jobs.run_verification(app.state.db, rid, sid, data / sid)
    r = c.get(f"/runs/{rid}").json()
    assert r["status"] == "done" and r["report"]["verdict"] == "PASS"
    rule = r["report"]["rules"][0]
    assert rule["reason_es"] and rule["evidence"][0]["frame_url"].startswith(f"/runs/{rid}/frames/")
    assert c.get(rule["evidence"][0]["frame_url"]).headers["content-type"] == "image/jpeg"
    assert c.get(r["video_url"]).status_code == 200
    assert c.get(f"/procedures/{pid}/runs").json()[0]["verdict"] == "PASS"
    audit = c.get(f"/audit/{sid}").json()
    assert {a["kind"] for a in audit} == {"muse", "sam"}


def test_missing_object_fails_not_pass(ctx, monkeypatch):
    c, sid, app, data = ctx
    pid = analyze(c, sid, app, data)
    jobs.run_analysis(app.state.db, pid, sid, data / sid)
    d = c.get(f"/procedures/{pid}").json()["draft"]
    c.put(f"/procedures/{pid}/rules", json={"draft": {k: d[k] for k in ("objects", "zones", "rules")}})
    c.post(f"/procedures/{pid}/approve")
    monkeypatch.setattr(sam_client, "segment", lambda v, p, pid_, **kw: SamResult(pid_, [] if p == "yellow square" else fake_segment(v, p, pid_).detections))
    rid = c.post(f"/procedures/{pid}/runs/from-sample", json={"sample_id": "run_missing_b"}).json()["run_id"]
    jobs.run_verification(app.state.db, rid, sid, data / sid)
    rep = c.get(f"/runs/{rid}").json()["report"]
    assert rep["verdict"] == "FAIL" and {r["rule_id"]: r["reason"] for r in rep["rules"]}["R2"] == "OBJECT_NOT_FOUND"


def test_model_failure_is_retryable_and_keeps_session(ctx, monkeypatch):
    c, sid, app, data = ctx
    def boom(video):
        raise ModelCallError("Muse Spark respondió HTTP 503.", retryable=True)
    monkeypatch.setattr(muse_client, "propose", boom)
    pid = analyze(c, sid, app, data)
    jobs.run_analysis(app.state.db, pid, sid, data / sid)
    v = c.get(f"/procedures/{pid}").json()
    assert v["status"] == "failed" and v["analysis"]["error"]["retryable"] is True
    assert [s["state"] for s in v["analysis"]["stages"]][:2] == ["done", "failed"]
    assert c.post(f"/procedures/{pid}/retry").status_code == 202
    assert c.get(f"/sessions/{sid}/procedures").json()[0]["status"] == "analyzing"


def test_invalid_video_is_actionable(ctx):
    c, sid, app, data = ctx
    r = c.post(f"/sessions/{sid}/procedures/from-video", data={"name": "x"}, files={"video": ("a.mp4", b"no es video", "video/mp4")})
    pid = r.json()["procedure_id"]
    jobs.run_analysis(app.state.db, pid, sid, data / sid)
    v = c.get(f"/procedures/{pid}").json()
    assert v["status"] == "failed" and "video" in v["analysis"]["error"]["message"].lower()
    assert v["analysis"]["error"]["retryable"] is False


def test_delete_session_removes_files(ctx):
    c, sid, app, data = ctx
    analyze(c, sid, app, data)
    assert (data / sid).exists()
    assert c.delete(f"/sessions/{sid}").status_code == 204
    assert not (data / sid).exists()
