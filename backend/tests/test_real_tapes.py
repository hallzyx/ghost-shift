"""Video REAL (cámara en mano, 3 cintas apiladas) con respuestas de SAM 3.1 grabadas (solo cajas) y el registro
de cámara calculado sobre los fotogramas reales. Sin red ni video: fixtures en fixtures/real_tapes/.

Clips: reference = grabación original (verde abajo, azul en medio, beige arriba); run_reversed = el mismo video
invertido en el tiempo (acaba con las cintas en fila); run_flipped = volteado vertical (torre al revés, artificial);
run_whip = pan rápido + desenfoque entre 2,5 y 7,5 s; run_shaky = recorte 72 % con barrido de ±40 % de la diagonal.
"""
import json
from pathlib import Path

import numpy as np
import pytest
from ghostshift_engine import Procedure, Verdict, compile_procedure, verify_run

from app import camera
from app.jobs import camera_view
from app.meta.sam_adapter import SamResult, build_trackset, parse_deltas
from app.pipeline.propose import propose_draft

FIX = Path(__file__).parent / "fixtures" / "real_tapes"
OBJECTS = [{"id": "A", "label_es": "Cinta azul", "sam_prompt": "blue tape roll"},
           {"id": "B", "label_es": "Cinta verde", "sam_prompt": "green tape roll"},
           {"id": "C", "label_es": "Cinta marrón", "sam_prompt": "brown tape roll"}]


def load(name):
    d = json.loads((FIX / f"{name}.json").read_text())
    results = [SamResult(pid, parse_deltas(r["deltas"]), r["video_frames_processed"]) for pid, r in d["sam"].items()]
    ts = build_trackset(name, "", d["video"], results)
    g = d["registration"]
    reg = camera.ClipRegistration(g["status"], g["anchor"], g["H"], g["registered_ratio"], g["max_shift"], g["texture_kp"])
    cross = None if d["cross"] is None else np.array(d["cross"]).reshape(3, 3)
    return ts, reg, cross, d


@pytest.fixture(scope="module")
def procedure():
    ts, reg, _, _ = load("reference")
    cam = camera.calibrate(reg, None, 0, False, ts)
    draft = propose_draft(cam.tracks, OBJECTS, {"uncertainties": []})
    return draft, compile_procedure(Procedure.model_validate(
        {"procedure_id": "real", "approved_by_user": True, **{k: draft[k] for k in ("objects", "zones", "rules")}}))


def run(proc, name, has_ref=True):
    ts, reg, cross, d = load(name)
    if reg.status == "unstable":
        cross = None
    if name == "reference":
        cross = np.eye(3)  # el mismo video: ancla idéntica (en la app el registro entre clips da desplazamiento 0)
    cam = camera.calibrate(reg, cross, d["cross_inliers"], has_ref, ts)
    rep = verify_run(proc, cam.tracks, cam.calibration)
    return rep, {r.rule_id: (r.verdict, r.reason) for r in rep.rules}, cam


def test_green_prompt_matches_all_three_tapes():
    """Hallazgo real: «green tape roll» devuelve 3 instancias (las tres cintas) en los 99 fotogramas."""
    ts, *_ = load("reference")
    assert {tl.track_id for tl in ts.tracklets if tl.prompt_id == "obj:B"} == {"obj:B#0", "obj:B#1", "obj:B#2"}


def test_handheld_camera_is_measured_and_compensated():
    ts, reg, _, _ = load("reference")
    assert reg.status == "compensated" and reg.registered_ratio == 1.0 and reg.max_shift > 0.10
    cam = camera.calibrate(reg, None, 0, False, ts)
    raw = [o for tl in ts.tracklets if tl.track_id == "obj:A#0" for o in tl.obs if o.f <= 15]
    reg_ = [o for tl in cam.tracks.tracklets if tl.track_id == "obj:A#0" for o in tl.obs if o.f <= 15]
    spread = lambda obs: np.ptp([(o.bbox[0] + o.bbox[2]) / 2 for o in obs])  # noqa: E731
    # la cinta azul está quieta el primer 1,5 s: en el video se desplaza ~37 px; registrada, ~3 px
    assert spread(raw) > 0.03 and spread(reg_) < 0.006


def test_proposes_stack_rules_instead_of_zone_only(procedure):
    draft, _ = procedure
    stacks = {(r["object"], r["base"]) for r in draft["rules"] if r["type"] == "stacked_on"}
    assert stacks == {("A", "B"), ("C", "A")}  # azul sobre verde, beige sobre azul
    assert not [r for r in draft["rules"] if r["type"] == "before"]  # implícito en el apilado
    assert any("Cámara en mano" in u or "apilado" in u for u in draft["uncertainties"])


def test_same_video_passes(procedure):
    _, proc = procedure
    rep, r, cam = run(proc, "reference")
    assert rep.verdict is Verdict.PASS, r
    assert r["R4"] == (Verdict.PASS, "STACKED") and r["R5"] == (Verdict.PASS, "STACKED")
    assert rep.camera_status == "RECALIBRATED"


def test_unstacked_tapes_fail_even_if_zone_rules_would_pass(procedure):
    _, proc = procedure
    rep, r, _ = run(proc, "run_reversed")
    assert r["R4"] == (Verdict.FAIL, "NOT_STACKED") and r["R5"] == (Verdict.FAIL, "NOT_STACKED")
    assert rep.verdict is Verdict.FAIL


def test_inverted_tower_fails_and_mirror_is_not_aligned(procedure):
    _, proc = procedure
    rep, r, cam = run(proc, "run_flipped")
    assert r["R4"] == (Verdict.FAIL, "STACK_INVERTED") and r["R5"] == (Verdict.FAIL, "STACK_INVERTED")
    assert {r[k][1] for k in ("R1", "R2", "R3")} == {"CAMERA_MOVED"}
    assert camera_view(rep.camera_status, cam.info)["aligned_to_reference"] is False


def test_shaky_cropped_camera_still_passes(procedure):
    _, proc = procedure
    rep, r, cam = run(proc, "run_shaky")
    assert cam.info["max_shift"] > 0.3 and rep.verdict is Verdict.PASS, r


def test_unregistrable_camera_is_review_not_pass_or_fail(procedure):
    _, proc = procedure
    rep, r, cam = run(proc, "run_whip")
    assert rep.verdict is Verdict.REVIEW and rep.blocking_issues == ["CAMERA_UNSTABLE"]
    assert cam.info["registered_ratio"] < 0.8
    assert "demasiado" in camera_view(rep.camera_status, cam.info)["message_es"]
