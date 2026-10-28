import pytest
from fastapi.testclient import TestClient
from ghostshift_engine.synth import SynthObject, make_trackset

from app.main import create_app

DRAFT = {
    "objects": [{"id": "A", "ref_max_score": 0.9}, {"id": "B", "ref_max_score": 0.9}],
    "zones": [
        {"id": "workspace", "role": "workspace", "polygon": [[0.05, 0.1], [0.95, 0.1], [0.95, 0.95], [0.05, 0.95]]},
        {"id": "left", "polygon": [[0.1, 0.4], [0.3, 0.4], [0.3, 0.6], [0.1, 0.6]]},
        {"id": "right", "polygon": [[0.7, 0.4], [0.9, 0.4], [0.9, 0.6], [0.7, 0.6]]},
    ],
    "rules": [
        {"id": "R1", "type": "in_zone_at", "object": "A", "zone": "left", "at": "end"},
        {"id": "R3", "type": "before", "first": "place:A", "second": "place:B"},
    ],
}


def tracks(order="AB"):
    ta, tb = (2000, 6000) if order == "AB" else (6000, 2000)
    objs = [
        SynthObject("A", [(0, 0.02, 0.5), (ta, 0.02, 0.5), (ta + 800, 0.2, 0.5)], visible_from_ms=ta - 600),
        SynthObject("B", [(0, 0.98, 0.5), (tb, 0.98, 0.5), (tb + 800, 0.8, 0.5)], visible_from_ms=tb - 600),
    ]
    return make_trackset(objs).model_dump(mode="json")


@pytest.fixture
def api():
    c = TestClient(create_app())
    sid = c.post("/sessions", json={"consent": True}).json()["session_id"]
    pid = c.post(f"/sessions/{sid}/procedures", json={"name": "kit", "draft": DRAFT}).json()["procedure_id"]
    return c, sid, pid


def test_consent_required():
    assert TestClient(create_app()).post("/sessions", json={}).status_code == 400


def test_cannot_verify_with_draft(api):
    c, _, pid = api
    assert c.post(f"/procedures/{pid}/runs/from-tracks", json=tracks()).status_code == 409


def test_full_flow_and_versioning(api):
    c, sid, pid = api
    assert c.post(f"/procedures/{pid}/approve").json()["version"] == 1
    ok = c.post(f"/procedures/{pid}/runs/from-tracks", json=tracks("AB")).json()
    bad = c.post(f"/procedures/{pid}/runs/from-tracks", json=tracks("BA")).json()
    assert (ok["verdict"], bad["verdict"]) == ("PASS", "FAIL")
    assert c.get(f"/runs/{bad['run_id']}").json()["procedure_version"] == 1
    # editar tras aprobar crea v2 borrador; las ejecuciones siguen usando la v1 aprobada
    assert c.put(f"/procedures/{pid}/rules", json={"draft": DRAFT}).json() == {
        "procedure_id": pid, "version": 2, "status": "draft"}
    run = c.post(f"/procedures/{pid}/runs/from-tracks", json=tracks()).json()
    assert c.get(f"/runs/{run['run_id']}").json()["procedure_version"] == 1


def test_approve_rejects_invalid_rules(api):
    c, _, pid = api
    bad = {**DRAFT, "rules": [{"id": "R", "type": "before", "first": "place:A", "second": "place:A"}]}
    c.put(f"/procedures/{pid}/rules", json={"draft": bad})
    assert c.post(f"/procedures/{pid}/approve").status_code == 422


def test_delete_session_removes_everything(api):
    c, sid, pid = api
    assert c.delete(f"/sessions/{sid}").status_code == 204
    assert c.get(f"/audit/{sid}").status_code == 404
    assert c.post(f"/procedures/{pid}/approve").status_code == 404
