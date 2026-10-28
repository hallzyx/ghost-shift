"""Compuertas, regla de oro de FAIL y agregación global (spec §4.1, §4.2, §4.6)."""
from __future__ import annotations

from dataclasses import dataclass

from .contracts.params import EngineParams
from .contracts.procedure import CompiledProcedure, Rule, parse_event_ref
from .contracts.results import Outcome, RuleResult, RunReport, Tri, Verdict
from .contracts.tracks import TrackSet
from .events import detect_events
from .features import build_timelines
from .rules import REGISTRY, Ctx
from .version import ENGINE_VERSION

_VERDICT = {Tri.TRUE: Verdict.PASS, Tri.FALSE: Verdict.FAIL, Tri.UNKNOWN: Verdict.REVIEW}


@dataclass(frozen=True)
class CalibrationResult:
    status: str = "ALIGNED"  # ALIGNED | RECALIBRATED | INCOMPATIBLE
    camera_moved: bool = False


def rule_objects(rule: Rule) -> set[str]:
    if rule.type == "before":
        return {parse_event_ref(rule.first)[0], parse_event_ref(rule.second)[0]}
    return {rule.object}


def verify_run(
    proc: CompiledProcedure,
    tracks: TrackSet,
    calibration: CalibrationResult | None = None,
    unconfirmed_objects: frozenset[str] = frozenset(),
    params: EngineParams | None = None,
) -> RunReport:
    params = params or EngineParams()
    cal = calibration or CalibrationResult()
    timelines = build_timelines(tracks, proc, params)
    logs = {o: detect_events(tl, proc, tracks, params) for o, tl in timelines.items()}
    ctx = Ctx(proc, tracks, params, timelines, logs)

    blocking: list[str] = []
    global_reason: str | None = None
    if cal.status == "INCOMPATIBLE":
        global_reason = "CAMERA_INCOMPATIBLE"
    elif not any(
        sum(1 for _ in tl.visible()) * 1000 / tracks.clip.analysis_fps >= params.presence_min_ms
        for tl in timelines.values()
    ):
        global_reason = "INSUFFICIENT_OBSERVATION"
    if global_reason:
        blocking.append(global_reason)

    results: list[RuleResult] = []
    for rule in proc.procedure.rules:
        if not rule.enabled:
            results.append(RuleResult(rule.id, rule.text_es, Verdict.SKIPPED, "DISABLED"))
            continue
        if global_reason:
            out = Outcome(Tri.UNKNOWN, global_reason)
        elif cal.camera_moved and rule.type != "before":
            out = Outcome(Tri.UNKNOWN, "CAMERA_MOVED")
        elif rule_objects(rule) & unconfirmed_objects:
            out = Outcome(Tri.UNKNOWN, "IDENTITY_UNCONFIRMED")
        else:
            out = REGISTRY[rule.type](rule, ctx)
        if out.value is Tri.FALSE and not any(
            e.kind in ("event", "state", "absence_probe") for e in out.evidence
        ):
            out = Outcome(Tri.UNKNOWN, "INTERNAL_NO_EVIDENCE", out.evidence, out.missing)
        results.append(RuleResult(rule.id, rule.text_es, _VERDICT[out.value], out.reason,
                                  list(out.evidence), list(out.missing)))

    active = [r.verdict for r in results if r.verdict is not Verdict.SKIPPED]
    if global_reason:
        overall = Verdict.REVIEW
    elif Verdict.FAIL in active:
        overall = Verdict.FAIL
    elif Verdict.REVIEW in active:
        overall = Verdict.REVIEW
    else:
        overall = Verdict.PASS
    events = [e for lg in logs.values() for e in lg.events]
    return RunReport(proc.procedure.procedure_id, proc.procedure.version, proc.content_hash, overall,
                     results, blocking, events, params.hash(), ENGINE_VERSION, cal.status)
