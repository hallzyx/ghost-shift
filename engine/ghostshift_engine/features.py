"""Rasgos por fotograma y estado de observación (spec §3.1)."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .contracts.params import EngineParams
from .contracts.procedure import CompiledProcedure
from .contracts.tracks import FrameObs, TrackSet
from .geometry import bbox_area, bbox_center, bbox_fraction_in, bbox_intersection, expand_bbox

VISIBLE, OCCLUDED, ABSENT, UNOBSERVED = "VISIBLE", "OCCLUDED", "ABSENT", "UNOBSERVED"
HAND_PROMPT = "aux:hand"


@dataclass
class ObjectTimeline:
    obj: str
    state: list[str]
    bbox: list[tuple[float, float, float, float] | None]
    score: list[float]
    inside: dict[str, np.ndarray]
    hand_near: list[bool] = field(default_factory=list)

    def center(self, f: int) -> tuple[float, float]:
        return bbox_center(self.bbox[f])

    def visible(self) -> list[int]:
        return [f for f, s in enumerate(self.state) if s == VISIBLE]

    def detected_any(self) -> bool:
        return any(s in (VISIBLE, OCCLUDED) for s in self.state)


def _best_per_frame(tracksets, prompt: str) -> tuple[dict[int, FrameObs], tuple[int, int] | None]:
    best: dict[int, FrameObs] = {}
    lo = hi = None
    for tl in tracksets.tracklets:
        if tl.prompt_id != prompt:
            continue
        lo = tl.processed_frames[0] if lo is None else min(lo, tl.processed_frames[0])
        hi = tl.processed_frames[1] if hi is None else max(hi, tl.processed_frames[1])
        for o in tl.obs:
            if o.f not in best or o.score > best[o.f].score:
                best[o.f] = o
    return best, (None if lo is None else (lo, hi))


def build_timelines(
    tracks: TrackSet, proc: CompiledProcedure, params: EngineParams
) -> dict[str, ObjectTimeline]:
    n = len(tracks.clip.frame_t_ms)
    hands, _ = _hands(tracks)
    out: dict[str, ObjectTimeline] = {}
    for o in proc.procedure.objects:
        best, proc_range = _best_per_frame(tracks, f"obj:{o.id}")
        areas = sorted(bbox_area(x.bbox) for x in (
            [b for b in best.values() if b.score >= 0.7] or list(best.values())))
        area_ref = areas[len(areas) // 2] if areas else 0.0
        state: list[str] = []
        bboxes: list = []
        score: list[float] = []
        near: list[bool] = []
        inside = {z: np.zeros(n) for z in proc.grids}
        for f in range(n):
            ob = best.get(f)
            if ob is None:
                in_range = proc_range is not None and proc_range[0] <= f <= proc_range[1]
                state.append(ABSENT if in_range else UNOBSERVED)
                bboxes.append(None)
                score.append(0.0)
                near.append(False)
                continue
            bboxes.append(ob.bbox)
            score.append(ob.score)
            area = bbox_area(ob.bbox)
            hand_boxes = hands.get(f, [])
            occl = max((bbox_intersection(ob.bbox, h) / area for h in hand_boxes), default=0.0) if area else 0.0
            near.append(any(bbox_intersection(expand_bbox(ob.bbox, 0.3), h) > 0 for h in hand_boxes))
            ok = ob.score >= params.score_visible and area >= params.frag_ratio * area_ref and occl < params.hand_occl
            state.append(VISIBLE if ok else OCCLUDED)
            for z, grid in proc.grids.items():
                inside[z][f] = bbox_fraction_in(grid, ob.bbox)
        out[o.id] = ObjectTimeline(o.id, state, bboxes, score, inside, near)
    return out


def _hands(tracks: TrackSet):
    by_frame: dict[int, list] = {}
    for tl in tracks.tracklets:
        if tl.prompt_id == HAND_PROMPT:
            for ob in tl.obs:
                by_frame.setdefault(ob.f, []).append(ob.bbox)
    return by_frame, bool(by_frame)
