"""Generador de pistas sintéticas para probar el motor sin modelos (spec §7)."""
from __future__ import annotations

import random
from dataclasses import dataclass, field

from .contracts.tracks import AbsenceProbe, ClipMeta, FrameObs, TrackSet, Tracklet


@dataclass
class SynthObject:
    id: str
    waypoints: list[tuple[int, float, float]]  # (t_ms, cx, cy), interpolación lineal
    size: tuple[float, float] = (0.08, 0.08)
    visible_from_ms: int = 0
    visible_to_ms: int | None = None
    hidden: list[tuple[int, int]] = field(default_factory=list)  # sin detección
    occluded: list[tuple[int, int]] = field(default_factory=list)  # mano encima


def _pos(wps, t):
    if t <= wps[0][0]:
        return wps[0][1], wps[0][2]
    for (t0, x0, y0), (t1, x1, y1) in zip(wps, wps[1:]):
        if t <= t1:
            a = (t - t0) / (t1 - t0) if t1 > t0 else 1.0
            return x0 + (x1 - x0) * a, y0 + (y1 - y0) * a
    return wps[-1][1], wps[-1][2]


def make_trackset(
    objects: list[SynthObject],
    duration_ms: int = 12000,
    fps: float = 10.0,
    noise: float = 0.002,
    seed: int = 0,
    probes: dict[str, float] | None = None,
    drop_prob: float = 0.0,
    width: int = 1280,
    height: int = 720,
) -> TrackSet:
    rng = random.Random(seed)
    step = 1000.0 / fps
    t = [round(i * step) for i in range(int(duration_ms / step) + 1)]
    n = len(t)
    tracklets, hand_obs = [], []
    for o in objects:
        obs = []
        for f, tm in enumerate(t):
            if tm < o.visible_from_ms or (o.visible_to_ms is not None and tm > o.visible_to_ms):
                continue
            if any(a <= tm <= b for a, b in o.hidden) or rng.random() < drop_prob:
                continue
            cx, cy = _pos(o.waypoints, tm)
            cx += rng.uniform(-noise, noise)
            cy += rng.uniform(-noise, noise)
            w, h = o.size
            bb = (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)
            score = 0.9
            if any(a <= tm <= b for a, b in o.occluded):
                hand_obs.append(FrameObs(f=f, score=0.85, bbox=(bb[0] - 0.02, bb[1] - 0.02, bb[2] + 0.02, bb[3] + 0.02)))
                score = 0.35
            obs.append(FrameObs(f=f, score=score, bbox=bb))
        tracklets.append(Tracklet(track_id=f"t-{o.id}", prompt_id=f"obj:{o.id}", obs=obs, processed_frames=(0, n - 1)))
    tracklets.append(Tracklet(track_id="t-hand", prompt_id="aux:hand", obs=hand_obs, processed_frames=(0, n - 1)))
    pr = [AbsenceProbe(prompt_id=f"obj:{k}", frames=list(range(n - 5, n)), max_score=v)
          for k, v in (probes or {}).items()]
    clip = ClipMeta(clip_id=f"synth-{seed}", width=width, height=height, analysis_fps=fps,
                    frame_t_ms=t, duration_ms=duration_ms)
    return TrackSet(clip=clip, tracklets=tracklets, absence_probes=pr)
