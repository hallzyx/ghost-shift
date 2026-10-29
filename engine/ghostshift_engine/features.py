"""Rasgos por fotograma y estado de observación (spec §3.1)."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .contracts.params import EngineParams
from .contracts.procedure import CompiledProcedure
from .contracts.tracks import FrameObs, TrackSet
from .geometry import bbox_area, bbox_center, bbox_fraction_in, bbox_intersection, bbox_iou, expand_bbox

VISIBLE, OCCLUDED, ABSENT, UNOBSERVED = "VISIBLE", "OCCLUDED", "ABSENT", "UNOBSERVED"
# Identidad dudosa en el fotograma: la caja coincide con la de otro objeto o el prompt devolvió varias
# instancias distintas sin poder decidir cuál es. Nunca cuenta como visible ni como ausente.
AMBIGUOUS = "AMBIGUOUS"
HAND_PROMPT = "aux:hand"


@dataclass
class ObjectTimeline:
    obj: str
    state: list[str]
    bbox: list[tuple[float, float, float, float] | None]
    score: list[float]
    inside: dict[str, np.ndarray]
    hand_near: list[bool] = field(default_factory=list)
    edge: list[bool | None] = field(default_factory=list)
    # OCCLUDED solo por caja reducida (parte tapada por otro objeto, no por la mano y con score suficiente)
    partial: list[bool] = field(default_factory=list)

    def center(self, f: int) -> tuple[float, float]:
        return bbox_center(self.bbox[f])

    def visible(self) -> list[int]:
        return [f for f, s in enumerate(self.state) if s == VISIBLE]

    def detected_any(self) -> bool:
        return any(s in (VISIBLE, OCCLUDED, AMBIGUOUS) for s in self.state)

    def at_edge(self, f: int, margin: float) -> bool:
        """Contacto con el borde del fotograma original (si el adaptador lo dio) o de la caja."""
        if f < len(self.edge) and self.edge[f] is not None:
            return bool(self.edge[f])
        b = self.bbox[f]
        return b[0] <= margin or b[1] <= margin or b[2] >= 1 - margin or b[3] >= 1 - margin


def _candidates(tracks: TrackSet, prompt: str) -> tuple[dict[int, list[tuple[str, FrameObs]]], tuple[int, int] | None]:
    cands: dict[int, list[tuple[str, FrameObs]]] = {}
    lo = hi = None
    for tl in tracks.tracklets:
        if tl.prompt_id != prompt:
            continue
        lo = tl.processed_frames[0] if lo is None else min(lo, tl.processed_frames[0])
        hi = tl.processed_frames[1] if hi is None else max(hi, tl.processed_frames[1])
        for o in tl.obs:
            cands.setdefault(o.f, []).append((tl.track_id, o))
    return cands, (None if lo is None else (lo, hi))


def _merge_same(obs: list[tuple[str, FrameObs]], dup_iou: float) -> list[tuple[str, FrameObs]]:
    """Instancias del mismo prompt que se solapan casi por completo son la misma cosa: queda la de más score."""
    out: list[tuple[str, FrameObs]] = []
    for tid, o in sorted(obs, key=lambda x: (-x[1].score, x[1].bbox, x[0])):
        if not any(bbox_iou(o.bbox, k.bbox) >= dup_iou for _, k in out):
            out.append((tid, o))
    return out


def resolve_identities(tracks: TrackSet, ids: list[str], params: EngineParams):
    """Una observación por objeto y fotograma, o AMBIGUOUS. Determinista.

    SAM devuelve TODAS las instancias que encajan con el concepto (p. ej. «green tape roll» también marcó
    las cintas azul y beige). 1) Un objeto con una única candidata la fija. 2) A uno con varias se le quitan
    las candidatas que coinciden con la caja fijada de otro objeto; si queda una, es esa. 3) Si siguen
    quedando varias, se usa la continuidad del id de seguimiento de SAM: la del mismo tracklet que el
    fotograma resuelto más cercano (antes; si no, después). 4) Si no, AMBIGUOUS. 5) Si dos objetos acaban
    con la misma caja, ambos son AMBIGUOUS.
    """
    cands, ranges = {}, {}
    for oid in ids:
        cands[oid], ranges[oid] = _candidates(tracks, f"obj:{oid}")
    n = len(tracks.clip.frame_t_ms)
    pending: dict[str, dict[int, list[tuple[str, FrameObs]]]] = {oid: {} for oid in ids}
    resolved: dict[str, dict[int, tuple[str, FrameObs]]] = {oid: {} for oid in ids}
    for f in range(n):
        per = {oid: _merge_same(cands[oid].get(f, []), params.dup_iou) for oid in ids}
        fixed = {oid: c[0][1] for oid, c in per.items() if len(c) == 1}
        for oid, c in per.items():
            rest = c if len(c) <= 1 else [
                (tid, o) for tid, o in c
                if not any(bbox_iou(o.bbox, fb.bbox) >= params.dup_iou for other, fb in fixed.items() if other != oid)]
            if len(rest) == 1:
                resolved[oid][f] = rest[0]
            elif c:
                pending[oid][f] = rest
    chosen: dict[str, dict[int, FrameObs | str]] = {oid: {f: o for f, (_, o) in resolved[oid].items()} for oid in ids}
    for oid in ids:
        frames_ok = sorted(resolved[oid])
        for f, rest in pending[oid].items():
            prev = [g for g in frames_ok if g < f]
            nxt = [g for g in frames_ok if g > f]
            pick = None
            for g in ([prev[-1]] if prev else []) + ([nxt[0]] if nxt else []):
                same = [x for x in rest if x[0] == resolved[oid][g][0]]
                if len(same) == 1:
                    pick = same[0][1]
                    break
            chosen[oid][f] = pick if pick is not None else AMBIGUOUS
    for f in range(n):
        picked = [(oid, v) for oid in ids if isinstance(v := chosen[oid].get(f), FrameObs)]
        for i, (a, oa) in enumerate(picked):
            for b, ob in picked[i + 1:]:
                if bbox_iou(oa.bbox, ob.bbox) >= params.dup_iou:
                    chosen[a][f] = chosen[b][f] = AMBIGUOUS
    return chosen, ranges


def build_timelines(
    tracks: TrackSet, proc: CompiledProcedure, params: EngineParams
) -> dict[str, ObjectTimeline]:
    n = len(tracks.clip.frame_t_ms)
    hands, _ = _hands(tracks)
    ids = [o.id for o in proc.procedure.objects]
    chosen, ranges = resolve_identities(tracks, ids, params)
    out: dict[str, ObjectTimeline] = {}
    for oid in ids:
        best = {f: v for f, v in chosen[oid].items() if isinstance(v, FrameObs)}
        proc_range = ranges[oid]
        areas = sorted(bbox_area(x.bbox) for x in (
            [b for b in best.values() if b.score >= 0.7] or list(best.values())))
        area_ref = areas[len(areas) // 2] if areas else 0.0
        state: list[str] = []
        bboxes: list = []
        score: list[float] = []
        near: list[bool] = []
        edge: list[bool | None] = []
        partial: list[bool] = []
        inside = {z: np.zeros(n) for z in proc.grids}
        for f in range(n):
            ob = best.get(f)
            if ob is None:
                in_range = proc_range is not None and proc_range[0] <= f <= proc_range[1]
                state.append(AMBIGUOUS if chosen[oid].get(f) == AMBIGUOUS else ABSENT if in_range else UNOBSERVED)
                bboxes.append(None)
                score.append(0.0)
                near.append(False)
                edge.append(None)
                partial.append(False)
                continue
            bboxes.append(ob.bbox)
            score.append(ob.score)
            edge.append(ob.edge)
            area = bbox_area(ob.bbox)
            hand_boxes = hands.get(f, [])
            occl = max((bbox_intersection(ob.bbox, h) / area for h in hand_boxes), default=0.0) if area else 0.0
            near.append(any(bbox_intersection(expand_bbox(ob.bbox, 0.3), h) > 0 for h in hand_boxes))
            ok = ob.score >= params.score_visible and area >= params.frag_ratio * area_ref and occl < params.hand_occl
            state.append(VISIBLE if ok else OCCLUDED)
            partial.append(not ok and ob.score >= params.score_visible and occl < params.hand_occl)
            for z, grid in proc.grids.items():
                inside[z][f] = bbox_fraction_in(grid, ob.bbox)
        out[oid] = ObjectTimeline(oid, state, bboxes, score, inside, near, edge, partial)
    return out


def _hands(tracks: TrackSet):
    by_frame: dict[int, list] = {}
    for tl in tracks.tracklets:
        if tl.prompt_id == HAND_PROMPT:
            for ob in tl.obs:
                by_frame.setdefault(ob.f, []).append(ob.bbox)
    return by_frame, bool(by_frame)
