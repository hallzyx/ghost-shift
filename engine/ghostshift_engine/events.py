"""Detector de eventos place/remove sobre la línea de tiempo de cada objeto (spec §3)."""
from __future__ import annotations

from dataclasses import dataclass, field
from statistics import median

from .contracts.params import EngineParams
from .contracts.procedure import CompiledProcedure
from .contracts.results import Event
from .contracts.tracks import TrackSet
from .features import VISIBLE, ObjectTimeline
from .geometry import dist_frac_diag


@dataclass
class EventLog:
    obj: str
    events: list[Event] = field(default_factory=list)
    initial_rest: tuple[int, str | None] | None = None  # (t_ms, zona)
    gaps: list[tuple[int, int]] = field(default_factory=list)
    identity_suspect: bool = False
    ends_moving: bool = False

    def places(self, zone: str | None = None) -> list[Event]:
        return [e for e in self.events if e.kind == "place" and (zone is None or e.zone == zone)]

    def removes(self) -> list[Event]:
        return [e for e in self.events if e.kind == "remove"]


def detect_events(
    tl: ObjectTimeline, proc: CompiledProcedure, tracks: TrackSet, params: EngineParams
) -> EventLog:
    t = tracks.clip.frame_t_ms
    fps = tracks.clip.analysis_fps
    w, h = tracks.clip.width, tracks.clip.height
    stable_n = params.n_frames(params.stable_ms, fps)
    exit_n = params.n_frames(params.exit_ms, fps)
    log = EventLog(tl.obj)
    vis = tl.visible()
    if not vis:
        return log

    def dist(a, b):
        return dist_frac_diag(a, b, w, h)

    def zone_of(f0: int, f1: int) -> str | None:
        best, best_v = None, 0.0
        for z in proc.target_zones:
            v = float(median(tl.inside[z][f0:f1 + 1]))
            if v >= params.theta_in and v > best_v:
                best, best_v = z, v
        return best

    def key_frame(f0: int, f1: int) -> int:
        return max(range(f0, f1 + 1), key=lambda i: (tl.score[i], -i) if tl.state[i] == VISIBLE else (-1, -i))

    def emit(kind, zone, t_lo, t_hi, kf, uncertain=False):
        k = sum(1 for e in log.events if e.kind == kind) + 1
        log.events.append(Event(kind, tl.obj, zone, k, t_lo, t_hi, kf, uncertain, log.identity_suspect))

    phase = "INIT"
    anchor = vis[0]
    anchor_pos = tl.center(anchor)
    run = 0
    rest_pos = anchor_pos
    cur_zone: str | None = None
    exit_run = 0
    exit_start = None
    last_in_f = vis[0]
    move_t_lo = t[vis[0]]
    gap_in_move = False
    entered_from_edge = tl.at_edge(vis[0], params.border_margin)

    for idx, f in enumerate(vis):
        prev = vis[idx - 1] if idx else None
        c = tl.center(f)
        consecutive = prev is not None and f == prev + 1
        if prev is not None:
            gap_ms = t[f] - t[prev]
            if not consecutive and gap_ms > params.max_gap_ms:
                log.gaps.append((t[prev], t[f]))
            if (consecutive and gap_ms <= params.jump_ms
                    and dist(c, tl.center(prev)) > params.jump_dist
                    and not (tl.hand_near[f] or tl.hand_near[prev])):
                log.identity_suspect = True
        if phase == "INIT":
            if idx == 0 or dist(c, anchor_pos) > params.still_eps:
                anchor, anchor_pos, run = f, c, 1
            else:
                run += 1
            if run >= stable_n:
                rest_pos, phase = anchor_pos, "RESTING"
                cur_zone = zone_of(anchor, f)
                last_in_f, exit_run = f, 0
                if entered_from_edge:
                    emit("place", cur_zone, t[vis[0]], t[anchor], key_frame(anchor, f),
                         uncertain=any(b != a + 1 for a, b in zip(vis, vis[1:]) if a < anchor))
                else:
                    log.initial_rest = (t[anchor], cur_zone)
        elif phase == "RESTING":
            if dist(c, rest_pos) > params.still_eps:
                phase = "MOVING"
                move_t_lo = t[prev] if prev is not None else t[f]
                anchor, anchor_pos, run = f, c, 1
                gap_in_move = not consecutive
                exit_run = 0
            elif cur_zone is not None:
                if tl.inside[cur_zone][f] < params.theta_out:
                    exit_run += 1
                    if exit_run == 1:
                        exit_start = f
                    if exit_run >= exit_n:
                        emit("remove", cur_zone, t[last_in_f], t[exit_start], key_frame(exit_start, f))
                        cur_zone = None
                else:
                    exit_run, last_in_f = 0, f
        else:  # MOVING
            if not consecutive:
                gap_in_move = True
            if dist(c, anchor_pos) > params.still_eps:
                anchor, anchor_pos, run = f, c, 1
            else:
                run += 1
            if run >= stable_n:
                if dist(anchor_pos, rest_pos) >= params.move_min:
                    emit("place", zone_of(anchor, f), move_t_lo, t[anchor], key_frame(anchor, f),
                         uncertain=gap_in_move)
                rest_pos, phase = anchor_pos, "RESTING"
                cur_zone = zone_of(anchor, f)
                last_in_f, exit_run = f, 0
    log.ends_moving = phase == "MOVING"
    return log
