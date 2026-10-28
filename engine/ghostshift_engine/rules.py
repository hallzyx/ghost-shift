"""Evaluadores de reglas con lógica de tres valores (spec §4). Añadir tipo = añadir función."""
from __future__ import annotations

from dataclasses import dataclass
from statistics import median
from typing import Callable

from .contracts.params import EngineParams
from .contracts.procedure import CompiledProcedure, Rule, parse_event_ref
from .contracts.results import Event, Evidence, Outcome, Tri
from .contracts.tracks import TrackSet
from .events import EventLog
from .features import VISIBLE, ObjectTimeline
from .geometry import touches_border


@dataclass
class Ctx:
    proc: CompiledProcedure
    tracks: TrackSet
    params: EngineParams
    timelines: dict[str, ObjectTimeline]
    logs: dict[str, EventLog]

    @property
    def t(self) -> list[int]:
        return self.tracks.clip.frame_t_ms


def _unknown(reason: str, missing: list[str] | None = None, ev: list[Evidence] | None = None) -> Outcome:
    return Outcome(Tri.UNKNOWN, reason, ev or [], missing or [])


def _state_ev(ctx: Ctx, obj: str, f: int, detail: str) -> Evidence:
    return Evidence("state", obj, ctx.t[f], f, detail)


def _event_ev(e: Event, detail: str = "") -> Evidence:
    return Evidence("event", e.obj, e.t_hi, e.frame_key, detail or f"{e.kind}:{e.obj}")


def absence_confirmed(ctx: Ctx, obj: str) -> Evidence | None:
    """Spec §4.4: ausencia solo si otros objetos se ven, el prompt se detectó en la referencia y el sondeo es bajo."""
    odef = next(o for o in ctx.proc.procedure.objects if o.id == obj)
    if odef.ref_max_score is None or odef.ref_max_score < ctx.params.ref_score_min:
        return None
    others_seen = any(
        len(tl.visible()) > 0 for oid, tl in ctx.timelines.items() if oid != obj)
    if not others_seen:
        return None
    for p in ctx.tracks.absence_probes:
        if p.prompt_id == f"obj:{obj}" and p.frames and p.max_score < ctx.params.absence_probe_max:
            f = max(p.frames)
            return Evidence("absence_probe", obj, ctx.t[f], f, f"sondeo max_score={p.max_score:.2f}")
    return None


def _zone(rule: Rule, ctx: Ctx) -> str:
    return rule.zone or ctx.proc.workspace_id


def eval_present_in_zone(rule: Rule, ctx: Ctx) -> Outcome:
    p, tl, zone = ctx.params, ctx.timelines[rule.object], _zone(rule, ctx)
    ins = tl.inside[zone]
    vis = tl.visible()
    runs, cur = [], []
    for f in vis:
        if ins[f] >= p.theta_in and (not cur or f == cur[-1] + 1):
            cur.append(f)
        else:
            if cur:
                runs.append(cur)
            cur = [f] if ins[f] >= p.theta_in else []
    if cur:
        runs.append(cur)
    for r in runs:
        if ctx.t[r[-1]] - ctx.t[r[0]] >= p.presence_min_ms:
            return Outcome(Tri.TRUE, "PRESENT", [_state_ev(ctx, rule.object, r[0], f"dentro de {zone}")])
    outside = [f for f in vis if ins[f] <= p.theta_out]
    if outside and ctx.t[outside[-1]] - ctx.t[outside[0]] >= p.presence_min_ms:
        return Outcome(Tri.FALSE, "OUT_OF_ZONE",
                       [_state_ev(ctx, rule.object, outside[0], f"visible fuera de {zone}")])
    if not tl.detected_any():
        ev = absence_confirmed(ctx, rule.object)
        if ev:
            return Outcome(Tri.FALSE, "OBJECT_NOT_FOUND", [ev])
    return _unknown("ABSENCE_UNCONFIRMED", ["confirmación de ausencia o visibilidad suficiente"])


def eval_in_zone_at(rule: Rule, ctx: Ctx) -> Outcome:
    return (_in_zone_end if rule.at == "end" else _in_zone_during)(rule, ctx)


def _in_zone_end(rule: Rule, ctx: Ctx) -> Outcome:
    p, tl, zone, t = ctx.params, ctx.timelines[rule.object], rule.zone, ctx.t
    win = [f for f in range(len(t)) if t[f] >= t[-1] - p.end_window_ms]
    vis = [f for f in win if tl.state[f] == VISIBLE]
    if len(vis) / len(win) < p.end_visible_ratio:
        allvis = tl.visible()
        if allvis and not vis and allvis[-1] < win[0] and touches_border(tl.bbox[allvis[-1]], p.border_margin):
            return Outcome(Tri.FALSE, "OBJECT_REMOVED",
                           [_state_ev(ctx, rule.object, allvis[-1], "última posición visible en el borde")])
        if not tl.detected_any():
            ev = absence_confirmed(ctx, rule.object)
            if ev:
                return Outcome(Tri.FALSE, "OBJECT_NOT_FOUND", [ev])
        return _unknown("NOT_VISIBLE_AT_END", ["visibilidad del objeto al finalizar"])
    med = float(median(tl.inside[zone][vis]))
    kf = max(vis, key=lambda f: tl.score[f])
    if med >= p.theta_in:
        return Outcome(Tri.TRUE, "IN_ZONE", [_state_ev(ctx, rule.object, kf, f"dentro de {zone} al final")])
    if med <= p.theta_out:
        return Outcome(Tri.FALSE, "OUT_OF_ZONE", [_state_ev(ctx, rule.object, kf, f"fuera de {zone} al final")])
    return _unknown("BORDERLINE_POSITION", ev=[_state_ev(ctx, rule.object, kf, "posición en el borde de la zona")])


def _anchor_time(ref: str, ctx: Ctx) -> int | None:
    if ref == "end":
        return ctx.t[-1]
    obj, zone = parse_event_ref(ref)
    ev = ctx.logs[obj].places(zone)
    return ev[0].t_hi if ev else None


def _in_zone_during(rule: Rule, ctx: Ctx) -> Outcome:
    p, tl, zone, t = ctx.params, ctx.timelines[rule.object], rule.zone, ctx.t
    t0, t1 = _anchor_time(rule.from_ or "", ctx) if rule.from_ else None, _anchor_time(rule.to or "end", ctx)
    if t0 is None or t1 is None:
        return _unknown("ANCHOR_EVENT_MISSING", ["evento de anclaje no observado"])
    for e in ctx.logs[rule.object].removes():
        if e.zone == zone and t0 <= e.t_hi <= t1:
            return Outcome(Tri.FALSE, "ZONE_EXITED", [_event_ev(e, f"salió de {zone}")])
    frames = [f for f in range(len(t)) if t0 <= t[f] <= t1]
    vis = [f for f in frames if tl.state[f] == VISIBLE]
    gaps = [g for g in ctx.logs[rule.object].gaps if g[0] < t1 and g[1] > t0]
    if frames and len(vis) / len(frames) >= p.during_coverage and not gaps \
            and float(median(tl.inside[zone][vis])) >= p.theta_in:
        return Outcome(Tri.TRUE, "STAYED_IN_ZONE", [_state_ev(ctx, rule.object, vis[0], f"permanece en {zone}")])
    return _unknown("DURING_NOT_VERIFIABLE", ["cobertura visible continua en el intervalo"])


def _pick(events: list[Event], mode: str) -> Event | None:
    if not events:
        return None
    return events[0] if mode == "first" else events[-1]


def _before_once(ev1: Event | None, ev2: Event | None, ref1: str, ctx: Ctx) -> Outcome:
    if ev1 and ev2:
        if ev1.identity_suspect or ev2.identity_suspect:
            return _unknown("IDENTITY_SUSPECT", ev=[_event_ev(ev1), _event_ev(ev2)])
        if ev1.t_hi < ev2.t_lo:
            return Outcome(Tri.TRUE, "ORDER_OK", [_event_ev(ev1), _event_ev(ev2)])
        if ev2.t_hi < ev1.t_lo:
            return Outcome(Tri.FALSE, "ORDER_VIOLATED", [_event_ev(ev2), _event_ev(ev1)])
        return _unknown("ORDER_OVERLAP", ["separación temporal entre colocaciones"],
                        [_event_ev(ev1), _event_ev(ev2)])
    if ev2 and not ev1:
        obj, _ = parse_event_ref(ref1)
        tl, log, p = ctx.timelines[obj], ctx.logs[obj], ctx.params
        upto = [f for f in range(len(ctx.t)) if ctx.t[f] <= ev2.t_lo]
        if log.initial_rest is not None and not log.places() and upto \
                and sum(tl.state[f] == VISIBLE for f in upto) / len(upto) >= p.coverage_min:
            return Outcome(Tri.FALSE, "FIRST_EVENT_MISSING_BEFORE_SECOND",
                           [_event_ev(ev2), _state_ev(ctx, obj, max(f for f in upto if tl.state[f] == VISIBLE),
                                                      f"{obj} sin colocarse antes de la segunda colocación")])
        return _unknown("ORDER_NOT_OBSERVED", ["colocación del primer objeto"])
    if ev1 and not ev2:
        return _unknown("EVENT_NOT_OCCURRED", ["colocación del segundo objeto"])
    return _unknown("ORDER_NOT_OBSERVED", ["colocaciones de ambos objetos"])


def eval_before(rule: Rule, ctx: Ctx) -> Outcome:
    o1, z1 = parse_event_ref(rule.first)
    o2, z2 = parse_event_ref(rule.second)
    l1, l2 = ctx.logs[o1].places(z1), ctx.logs[o2].places(z2)
    modes = ["first", "definitive"] if rule.occurrence == "both_agree" else [rule.occurrence]
    outs = [_before_once(_pick(l1, m), _pick(l2, m), rule.first, ctx) for m in modes]
    if len(outs) == 1 or outs[0].value == outs[1].value:
        return outs[0]
    return _unknown("ORDER_AMBIGUOUS_REPLACEMENT", ["decisión humana sobre recolocaciones"],
                    outs[0].evidence + outs[1].evidence)


REGISTRY: dict[str, Callable[[Rule, Ctx], Outcome]] = {
    "present_in_zone": eval_present_in_zone,
    "in_zone_at": eval_in_zone_at,
    "before": eval_before,
}
