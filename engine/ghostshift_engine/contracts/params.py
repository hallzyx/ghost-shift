"""Parámetros globales del motor (spec §3.3). Nunca por vídeo ni por procedimiento."""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class EngineParams:
    score_visible: float = 0.50
    frag_ratio: float = 0.55
    hand_occl: float = 0.15
    theta_in: float = 0.60
    theta_out: float = 0.35
    stable_ms: int = 600
    still_eps: float = 0.010  # fracción de la diagonal en píxeles
    move_min: float = 0.05
    exit_ms: int = 300
    max_gap_ms: int = 1000
    end_window_ms: int = 1000
    end_visible_ratio: float = 0.70
    presence_min_ms: int = 500
    coverage_min: float = 0.90
    during_coverage: float = 0.80
    jump_dist: float = 0.25
    jump_ms: int = 200
    absence_probe_max: float = 0.30
    ref_score_min: float = 0.70
    border_margin: float = 0.02
    dup_iou: float = 0.80  # dos cajas con este IoU son el mismo objeto físico (identidad)
    # stacked_on (orden vertical al final, spec §4.8)
    stack_overlap_min: float = 0.60  # solape horizontal / ancho del más estrecho
    stack_rise_min: float = 0.25  # el de arriba debe estar más alto: (cy_base - cy_top) / alto_base
    stack_gap_max: float = 0.50  # hueco vertical máx. entre el borde inferior del de arriba y el superior de la base
    stack_agree: float = 0.70  # fracción de fotogramas que deben coincidir para decidir
    stack_visible_ratio: float = 0.50  # fotogramas de la ventana final con ambos objetos visibles

    def n_frames(self, ms: float, fps: float) -> int:
        return max(1, math.ceil(ms * fps / 1000.0))

    def hash(self) -> str:
        blob = json.dumps(asdict(self), sort_keys=True).encode()
        return "sha256:" + hashlib.sha256(blob).hexdigest()
