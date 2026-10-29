"""Apilado (stacked_on), identidad entre objetos parecidos y compuertas de cámara."""
import pytest

from ghostshift_engine import CalibrationResult, ProcedureError, Verdict, verify_run
from ghostshift_engine.contracts.params import EngineParams
from ghostshift_engine.contracts.tracks import FrameObs, Tracklet
from ghostshift_engine.features import OCCLUDED, build_timelines
from ghostshift_engine.synth import SynthObject, make_trackset

from ..conftest import procedure

SIZE = (0.10, 0.08)
BASE = (0.50, 0.60)
ON_BASE = (0.50, 0.53)  # 0.07 más arriba: su borde inferior (0.57) pisa el superior de la base (0.56)
STACK = [{"id": "S1", "type": "stacked_on", "object": "A", "base": "B"}]


def stack_proc(rules=STACK, objects=("A", "B")):
    return procedure(rules=rules, objects=objects)


def run(a_end, b_end=BASE, **kw):
    """B en reposo; A llega desde el borde a a_end hacia los 4 s."""
    objs = [SynthObject("A", [(0, 0.02, 0.5), (3000, 0.02, 0.5), (4000, *a_end)], size=SIZE, visible_from_ms=2400, **kw),
            SynthObject("B", [(0, *b_end)], size=SIZE)]
    return make_trackset(objs, duration_ms=8000)


def verdicts(rep):
    return {r.rule_id: (r.verdict, r.reason) for r in rep.rules}


def test_stacked_pass_with_evidence():
    rep = verify_run(stack_proc(), run(ON_BASE))
    assert verdicts(rep)["S1"] == (Verdict.PASS, "STACKED") and rep.verdict is Verdict.PASS
    ev = rep.rules[0].evidence
    assert {e.obj for e in ev} == {"A", "B"} and "apilado" in ev[0].detail


def test_scattered_next_to_base_fails_not_stacked():
    rep = verify_run(stack_proc(), run((0.70, 0.60)))
    assert verdicts(rep)["S1"] == (Verdict.FAIL, "NOT_STACKED")


def test_wrong_order_fails_inverted():
    rep = verify_run(stack_proc(), run((0.50, 0.67)))  # A queda debajo de B
    assert verdicts(rep)["S1"] == (Verdict.FAIL, "STACK_INVERTED")


def test_floating_far_above_is_not_directly_on():
    rep = verify_run(stack_proc(), run((0.50, 0.35)))  # mismo eje vertical, pero con hueco grande (otro objeto entre medias)
    assert verdicts(rep)["S1"] == (Verdict.FAIL, "NOT_STACKED")


def test_hand_over_tower_at_end_is_review_not_pass():
    rep = verify_run(stack_proc(), run(ON_BASE, occluded=[(6500, 8000)]))
    assert verdicts(rep)["S1"] == (Verdict.REVIEW, "STACK_NOT_VISIBLE_AT_END")
    assert rep.verdict is Verdict.REVIEW


def test_partial_hiding_of_base_at_end_is_review():
    objs = [SynthObject("A", [(0, *ON_BASE)], size=SIZE),
            SynthObject("B", [(0, *BASE)], size=SIZE, hidden=[(7000, 8000)])]
    rep = verify_run(stack_proc(), make_trackset(objs, duration_ms=8000))
    assert verdicts(rep)["S1"] == (Verdict.REVIEW, "STACK_NOT_VISIBLE_AT_END")


def test_base_partly_hidden_by_the_top_object_still_counts():
    """En la torre real la cinta de abajo solo enseña su lateral: su caja encoge sin mano encima."""
    ts = run(ON_BASE)
    last = len(ts.clip.frame_t_ms) - 12
    for tl in ts.tracklets:
        if tl.prompt_id == "obj:B":
            tl.obs = [o if o.f < last else o.model_copy(update={"bbox": (o.bbox[0], 0.60, o.bbox[2], o.bbox[3])})
                      for o in tl.obs]
    rep = verify_run(stack_proc(), ts)
    tl_b = build_timelines(ts, stack_proc(), EngineParams())["B"]
    assert tl_b.state[-1] == OCCLUDED and tl_b.partial[-1]  # la caja encogida no es «visible» para zonas
    assert verdicts(rep)["S1"] == (Verdict.PASS, "STACKED")


def test_tower_of_three():
    rules = [{"id": "S1", "type": "stacked_on", "object": "B", "base": "A"},
             {"id": "S2", "type": "stacked_on", "object": "C", "base": "B"}]
    p = stack_proc(rules, objects=("A", "B", "C"))
    good = [SynthObject("A", [(0, 0.5, 0.62)], size=SIZE), SynthObject("B", [(0, 0.5, 0.55)], size=SIZE),
            SynthObject("C", [(0, 0.5, 0.48)], size=SIZE)]
    assert verify_run(p, make_trackset(good, duration_ms=6000)).verdict is Verdict.PASS
    swapped = [SynthObject("A", [(0, 0.5, 0.62)], size=SIZE), SynthObject("C", [(0, 0.5, 0.55)], size=SIZE),
               SynthObject("B", [(0, 0.5, 0.48)], size=SIZE)]
    r = verdicts(verify_run(p, make_trackset(swapped, duration_ms=6000)))
    assert r["S2"] == (Verdict.FAIL, "STACK_INVERTED") and r["S1"][0] is Verdict.FAIL


@pytest.mark.parametrize("bad", [
    [{"id": "S", "type": "stacked_on", "object": "A", "base": "A"}],
    [{"id": "S", "type": "stacked_on", "object": "A", "base": "Z"}],
    [{"id": "S1", "type": "stacked_on", "object": "A", "base": "B"},
     {"id": "S2", "type": "stacked_on", "object": "B", "base": "A"}],
    [{"id": "S1", "type": "stacked_on", "object": "A", "base": "B"},
     {"id": "S2", "type": "stacked_on", "object": "A", "base": "C"}],
])
def test_compile_rejects_invalid_stacks(bad):
    with pytest.raises(ProcedureError):
        stack_proc(bad, objects=("A", "B", "C"))


def _with_extra(ts, prompt, obs):
    ts.tracklets.append(Tracklet(track_id=f"{prompt}#x", prompt_id=prompt, obs=obs,
                                 processed_frames=(0, len(ts.clip.frame_t_ms) - 1)))
    return ts


def _obs_of(ts, prompt):
    return [o for tl in ts.tracklets if tl.prompt_id == prompt for o in tl.obs]


def test_prompt_matching_other_object_is_disambiguated():
    """Como «green tape roll», el prompt de B devuelve también la caja de A: se descarta y queda la de B."""
    ts = run(ON_BASE)
    ts = _with_extra(ts, "obj:B", [FrameObs(f=o.f, score=0.99, bbox=o.bbox) for o in _obs_of(ts, "obj:A")])
    assert verdicts(verify_run(stack_proc(), ts))["S1"] == (Verdict.PASS, "STACKED")


def test_two_remaining_instances_resolved_by_sam_track_continuity():
    """Como «blue tape roll» en el video invertido: desde la mitad aparece una 2.ª instancia (otra cinta sin
    prompt propio). Se mantiene el id de seguimiento que SAM ya daba a A; sin ese historial sería ambiguo."""
    ts = run((0.70, 0.60))
    n = len(ts.clip.frame_t_ms)
    ts = _with_extra(ts, "obj:A", [FrameObs(f=f, score=0.99, bbox=(0.2, 0.3, 0.3, 0.38)) for f in range(n // 2, n)])
    assert verdicts(verify_run(stack_proc(), ts))["S1"] == (Verdict.FAIL, "NOT_STACKED")
    for tl in ts.tracklets:  # sin historial previo de A: no hay forma de elegir
        if tl.track_id == "t-A":
            tl.obs = [o for o in tl.obs if o.f >= n // 2]
    assert verdicts(verify_run(stack_proc(), ts))["S1"] == (Verdict.REVIEW, "IDENTITY_CONFLICT")


def test_two_objects_with_the_same_box_are_identity_conflict():
    """Si el prompt de B solo encuentra la cinta A, no se puede saber dónde está B: REVIEW, nunca PASS."""
    ts = run(ON_BASE)
    last = len(ts.clip.frame_t_ms) - 15
    a_end = [FrameObs(f=o.f, score=0.9, bbox=o.bbox) for o in _obs_of(ts, "obj:A") if o.f >= last]
    for tl in ts.tracklets:
        if tl.prompt_id == "obj:B":
            tl.obs = [o for o in tl.obs if o.f < last] + a_end
    rep = verify_run(stack_proc(), ts)
    assert verdicts(rep)["S1"] == (Verdict.REVIEW, "IDENTITY_CONFLICT")


def test_camera_unstable_blocks_everything():
    rep = verify_run(stack_proc(), run(ON_BASE), CalibrationResult("INCOMPATIBLE", issue="CAMERA_UNSTABLE"))
    assert rep.verdict is Verdict.REVIEW and rep.blocking_issues == ["CAMERA_UNSTABLE"]
    assert verdicts(rep)["S1"] == (Verdict.REVIEW, "CAMERA_UNSTABLE")


def test_unaligned_with_reference_only_blocks_zone_rules():
    rules = STACK + [{"id": "Z1", "type": "in_zone_at", "object": "B", "zone": "workspace", "at": "end"}]
    rep = verify_run(stack_proc(rules), run(ON_BASE), CalibrationResult("ALIGNED", camera_moved=True))
    r = verdicts(rep)
    assert r["S1"] == (Verdict.PASS, "STACKED") and r["Z1"] == (Verdict.REVIEW, "CAMERA_MOVED")
    assert rep.verdict is Verdict.REVIEW


def test_edge_flag_from_adapter_overrides_box():
    """Con cajas transformadas a la referencia, «salir por el borde» se decide con el fotograma original."""
    objs = [SynthObject("A", [(0, 0.5, 0.5)]),
            SynthObject("B", [(0, 0.8, 0.5), (5000, 0.8, 0.5), (5600, 0.6, 0.5)], visible_to_ms=5800)]
    p = procedure(rules=[{"id": "R1", "type": "in_zone_at", "object": "B", "zone": "right", "at": "end"}])
    ts = make_trackset(objs, duration_ms=9000)
    assert verdicts(verify_run(p, ts))["R1"] == (Verdict.REVIEW, "NOT_VISIBLE_AT_END")
    for tl in ts.tracklets:
        if tl.prompt_id == "obj:B":
            tl.obs[-1] = tl.obs[-1].model_copy(update={"edge": True})
    assert verdicts(verify_run(p, ts))["R1"] == (Verdict.FAIL, "OBJECT_REMOVED")
