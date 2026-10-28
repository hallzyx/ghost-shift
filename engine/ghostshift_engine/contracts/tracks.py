"""Contrato de entrada: pistas que el adaptador de SAM entrega al motor (spec §1.2)."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ClipMeta(BaseModel):
    clip_id: str
    sha256: str = ""
    width: int
    height: int
    analysis_fps: float
    frame_t_ms: list[int]  # timestamp de cada fotograma analizado (monótono)
    duration_ms: int


class FrameObs(BaseModel):
    f: int  # índice en frame_t_ms
    score: float
    bbox: tuple[float, float, float, float]  # x0, y0, x1, y1 normalizados
    mask_rle: dict | None = None


class Tracklet(BaseModel):
    track_id: str  # solo válido dentro de este clip
    prompt_id: str  # "obj:A", "aux:hand"
    obs: list[FrameObs]  # fotogramas sin observación = ausentes de la lista
    processed_frames: tuple[int, int]  # rango [f0, f1] que SAM procesó


class AbsenceProbe(BaseModel):
    prompt_id: str
    frames: list[int]
    max_score: float


class ModelRef(BaseModel):
    model_id: str = "sam-3-1"
    version: str = ""
    request_ids: list[str] = Field(default_factory=list)


class TrackSet(BaseModel):
    schema_version: Literal["ghostshift.tracks/1"] = "ghostshift.tracks/1"
    clip: ClipMeta
    model: ModelRef = Field(default_factory=ModelRef)
    tracklets: list[Tracklet]
    absence_probes: list[AbsenceProbe] = Field(default_factory=list)
