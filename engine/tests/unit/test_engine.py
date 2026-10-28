import pytest

from ghostshift_engine import CalibrationResult, Procedure, ProcedureError, Verdict, compile_procedure, verify_run
from ghostshift_engine.synth import SynthObject, make_trackset

from ..conftest import LEFT, MID, RIGHT, place, procedure

OFF = (0.97, 0.50)  # fuera de plano (borde)


def scenario(order="AB", b_dest=RIGHT, **kw):
    """A y B entran desde el borde y se colocan; order decide quién primero."""
    t_a, t_b = (2000, 6000) if order == "AB" else (6000, 2000)
    objs = [
        SynthObject("A", [(0, 0.02, 0.5), (t_a, 0.02, 0.5), (t_a + 800, *LEFT)], visible_from_ms=t_a - 600),
        SynthObject("B", [(0, 0.98, 0.5), (t_b, 0.98, 0.5), (t_b + 800, *b_dest)], visible_from_ms=t_b - 600),
    ]
    return make_trackset(objs, **kw)


def rules_of(rep):
    return {r.rule_id: (r.verdict, r.reason) for r in rep.rules}


def test_happy_path_pass(proc):
    rep = verify_run(proc, scenario("AB"))
    assert rep.verdict is Verdict.PASS, rules_of(rep)


def test_wrong_order_same_final_state_fails_only_order(proc):
    rep = verify_run(proc, scenario("BA"))
    r = rules_of(rep)
    assert rep.verdict is Verdict.FAIL
    assert r["R1"][0] is Verdict.PASS and r["R2"][0] is Verdict.PASS
    assert r["R3"] == (Verdict.FAIL, "ORDER_VIOLATED")


def test_right_order_wrong_position_fails_position_not_order(proc):
    rep = verify_run(proc, scenario("AB", b_dest=MID))
    r = rules_of(rep)
    assert r["R3"][0] is Verdict.PASS
    assert r["R2"] == (Verdict.FAIL, "OUT_OF_ZONE")
    assert rep.verdict is Verdict.FAIL


def test_only_final_visible_order_is_review(proc):
    ts = make_trackset([SynthObject("A", [(0, *LEFT)]), SynthObject("B", [(0, *RIGHT)])])
    rep = verify_run(proc, ts)
    r = rules_of(rep)
    assert r["R1"][0] is Verdict.PASS and r["R3"] == (Verdict.REVIEW, "ORDER_NOT_OBSERVED")
    assert rep.verdict is Verdict.REVIEW


def test_hand_over_object_at_end_is_review_not_fail(proc):
    objs = [
        place("A", OFF, LEFT, 2000, visible_from_ms=1400),
        place("B", OFF, RIGHT, 6000, visible_from_ms=5400, occluded=[(9500, 12000)]),
    ]
    rep = verify_run(proc, make_trackset(objs))
    assert rules_of(rep)["R2"] == (Verdict.REVIEW, "NOT_VISIBLE_AT_END")
    assert rep.verdict is Verdict.REVIEW


def test_empty_segmentation_never_pass_or_fail(proc):
    rep = verify_run(proc, make_trackset([SynthObject("A", [(0, *LEFT)], hidden=[(0, 99999)]),
                                           SynthObject("B", [(0, *RIGHT)], hidden=[(0, 99999)])]))
    assert rep.verdict is Verdict.REVIEW and rep.blocking_issues == ["INSUFFICIENT_OBSERVATION"]


def test_missing_object_fails_only_with_absence_probe():
    p = procedure(rules=[{"id": "R1", "type": "present_in_zone", "object": "A", "zone": "workspace"},
                         {"id": "R2", "type": "present_in_zone", "object": "B", "zone": "workspace"}])
    objs = [SynthObject("A", [(0, *LEFT)]), SynthObject("B", [(0, *RIGHT)], hidden=[(0, 99999)])]
    no_probe = verify_run(p, make_trackset(objs))
    assert rules_of(no_probe)["R2"] == (Verdict.REVIEW, "ABSENCE_UNCONFIRMED")
    probed = verify_run(p, make_trackset(objs, probes={"B": 0.1}))
    assert rules_of(probed)["R2"] == (Verdict.FAIL, "OBJECT_NOT_FOUND")
    assert probed.rules[1].evidence[0].kind == "absence_probe"


def test_removed_object_at_end_fails():
    objs = [place("A", OFF, LEFT, 2000, visible_from_ms=1400),
            SynthObject("B", [(0, *RIGHT), (8000, *RIGHT), (8800, 0.99, 0.5)], visible_to_ms=9000)]
    p = procedure(rules=[{"id": "R1", "type": "in_zone_at", "object": "B", "zone": "right", "at": "end"}])
    rep = verify_run(p, make_trackset(objs))
    assert rules_of(rep)["R1"] == (Verdict.FAIL, "OBJECT_REMOVED")


def test_simultaneous_placement_is_overlap_review(proc):
    objs = [place("A", OFF, LEFT, 4000, visible_from_ms=3400),
            place("B", (0.98, 0.5), RIGHT, 4000, visible_from_ms=3400)]
    assert rules_of(verify_run(proc, make_trackset(objs)))["R3"] == (Verdict.REVIEW, "ORDER_OVERLAP")


def test_replacement_is_ambiguous_review(proc):
    a = SynthObject("A", [(0, 0.02, 0.5), (2000, 0.02, 0.5), (2800, *LEFT), (8000, *LEFT), (8800, 0.25, 0.55)],
                    visible_from_ms=1400)
    b = place("B", (0.98, 0.5), RIGHT, 5000, visible_from_ms=4400)
    r = rules_of(verify_run(proc, make_trackset([a, b])))
    assert r["R3"] == (Verdict.REVIEW, "ORDER_AMBIGUOUS_REPLACEMENT")


def test_camera_gates(proc):
    ts = scenario("AB")
    inc = verify_run(proc, ts, CalibrationResult("INCOMPATIBLE"))
    assert inc.verdict is Verdict.REVIEW and inc.blocking_issues == ["CAMERA_INCOMPATIBLE"]
    moved = verify_run(proc, ts, CalibrationResult("ALIGNED", camera_moved=True))
    assert rules_of(moved)["R1"] == (Verdict.REVIEW, "CAMERA_MOVED") and rules_of(moved)["R3"][0] is Verdict.PASS


def test_unconfirmed_identity_forces_review(proc):
    rep = verify_run(proc, scenario("AB"), unconfirmed_objects=frozenset({"B"}))
    assert rules_of(rep)["R2"] == (Verdict.REVIEW, "IDENTITY_UNCONFIRMED")
    assert rules_of(rep)["R1"][0] is Verdict.PASS


def test_disabled_rules_skipped_and_need_one_enabled(proc):
    p = procedure(rules=[{"id": "R1", "type": "in_zone_at", "object": "A", "zone": "left", "at": "end"},
                         {"id": "R2", "type": "in_zone_at", "object": "B", "zone": "right", "at": "end", "enabled": False}])
    rep = verify_run(p, scenario("AB", b_dest=MID))
    assert rep.verdict is Verdict.PASS and rep.rules[1].verdict is Verdict.SKIPPED
    with pytest.raises(ProcedureError):
        procedure(rules=[{"id": "R1", "type": "before", "first": "place:A", "second": "place:B", "enabled": False}])


def test_deterministic(proc):
    a, b = verify_run(proc, scenario("BA", seed=3)), verify_run(proc, scenario("BA", seed=3))
    assert a == b


@pytest.mark.parametrize("bad", [
    [{"id": "R", "type": "before", "first": "place:A", "second": "place:A"}],
    [{"id": "R", "type": "before", "first": "place:A", "second": "place:Z"}],
    [{"id": "R1", "type": "before", "first": "place:A", "second": "place:B"},
     {"id": "R2", "type": "before", "first": "place:B", "second": "place:A"}],
    [{"id": "R", "type": "in_zone_at", "object": "A", "zone": "nope", "at": "end"}],
])
def test_compile_rejects_invalid(bad):
    with pytest.raises(ProcedureError):
        procedure(rules=bad)


def test_unapproved_rejected():
    p = Procedure(procedure_id="x", approved_by_user=False, objects=[{"id": "A"}],
                  zones=[{"id": "w", "role": "workspace", "polygon": [(0, 0), (1, 0), (1, 1), (0, 1)]}],
                  rules=[{"id": "R", "type": "present_in_zone", "object": "A"}])
    with pytest.raises(ProcedureError):
        compile_procedure(p)
