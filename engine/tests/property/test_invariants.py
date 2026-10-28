import random

import pytest

from ghostshift_engine import Verdict, verify_run
from ghostshift_engine.synth import make_trackset

from ..conftest import procedure
from ..unit.test_engine import scenario


@pytest.mark.parametrize("order", ["AB", "BA"])
@pytest.mark.parametrize("seed", range(10))
def test_losing_data_only_moves_verdicts_toward_review(order, seed):
    """Monotonía: degradar la observación no puede cambiar el veredicto a otro distinto de REVIEW."""
    proc = procedure()
    base = verify_run(proc, scenario(order, seed=seed))
    degraded = verify_run(proc, scenario(order, seed=seed, drop_prob=random.Random(seed).uniform(0.1, 0.5)))
    base_by_rule = {r.rule_id: r.verdict for r in base.rules}
    for r in degraded.rules:
        assert r.verdict in (base_by_rule[r.rule_id], Verdict.REVIEW), (r.rule_id, r.reason)


@pytest.mark.parametrize("seed", range(10))
def test_noise_does_not_change_verdict(seed):
    proc = procedure()
    for order, expected in (("AB", Verdict.PASS), ("BA", Verdict.FAIL)):
        assert verify_run(proc, scenario(order, seed=seed, noise=0.003)).verdict is expected


@pytest.mark.parametrize("fps", [5.0, 10.0, 15.0])
def test_verdict_stable_across_fps(fps):
    proc = procedure()
    assert verify_run(proc, scenario("AB", fps=fps)).verdict is Verdict.PASS
    assert verify_run(proc, scenario("BA", fps=fps)).verdict is Verdict.FAIL


def test_fail_always_has_evidence():
    proc = procedure()
    for order in ("AB", "BA"):
        for r in verify_run(proc, scenario(order)).rules:
            if r.verdict is Verdict.FAIL:
                assert r.evidence
