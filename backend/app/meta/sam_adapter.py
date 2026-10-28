"""Adaptador SAM 3.1 -> TrackSet (docs/meta-findings.md, spec del motor §1.2).

Una petición SAM por concepto (``obj:A``, ``aux:hand``). Cada petición devuelve líneas
``<Nf>id<|box;...|><|mask;...|>``; aquí se convierten en tracklets normalizados.
"""
from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from fractions import Fraction
from typing import Iterable

from ghostshift_engine.contracts.tracks import (
    ClipMeta, FrameObs, ModelRef, TrackSet, Tracklet,
)

# Puntuación asumida cuando la petición no pidió include_confidence (no hay campo `c`).
DEFAULT_SCORE = 0.9

_LINE = re.compile(r"<(\d+)f>(.*)", re.S)
_RECORD = re.compile(r"(\d+)<\|box;([^|]*)\|>(?:<\|mask;([^|]*)\|>)?")


class SamParseError(ValueError):
    pass


@dataclass(frozen=True)
class SamDetection:
    frame: int
    object_id: int
    box: tuple[float, float, float, float]  # x1, y1, x2, y2 en píxeles del fotograma fuente
    width: int
    height: int
    score: float | None
    mask: dict | None = None  # {"data": "H,W,<marcador><payload>", "x": int, "y": int}


@dataclass(frozen=True)
class SamResult:
    prompt_id: str
    detections: list[SamDetection]
    frames_processed: int | None = None
    request_id: str | None = None


def _fields(text: str) -> dict[str, str]:
    out = {}
    for part in text.split(";"):
        if "=" in part:
            k, v = part.split("=", 1)
            out[k.strip()] = v
    return out


def parse_deltas(deltas: Iterable[str]) -> list[SamDetection]:
    """Parsea los ``response.output_text.delta`` (una línea por fotograma).

    Cero deltas es un resultado válido (ningún objeto coincide) y devuelve ``[]``.
    """
    out: list[SamDetection] = []
    for raw in deltas:
        m = _LINE.match(raw.strip())
        if not m:
            raise SamParseError(f"línea sin marcador de fotograma: {raw[:60]!r}")
        frame = int(m.group(1))
        for rec in _RECORD.finditer(m.group(2)):
            kv = _fields(rec.group(2))
            try:
                box = (float(kv["x1"]), float(kv["y1"]), float(kv["x2"]), float(kv["y2"]))
                w, h = int(kv["w"]), int(kv["h"])
            except KeyError as e:
                raise SamParseError(f"caja sin campo {e} en fotograma {frame}") from e
            mask = None
            if rec.group(3):
                mkv = _fields(rec.group(3).split("data=")[0])
                mask = {"data": rec.group(3).split("data=", 1)[1],
                        "x": int(mkv.get("x", 0)), "y": int(mkv.get("y", 0))}
            score = float(kv["c"]) if "c" in kv else None
            out.append(SamDetection(frame, int(rec.group(1)), box, w, h, score, mask))
    return out


def decode_mask_rle(mask: dict) -> dict:
    """Decodifica una máscara base85 (``~`` sin pérdida, ``!`` 1 bit) a RLE COCO.

    Requiere el parser oficial ``meta-sam-parser`` (extra ``sam-masks``). La máscara es el
    recorte de la caja del objeto a su propia resolución; (x, y) es el desplazamiento en
    ese recorte.
    """
    from meta_sam_parser import SegmentationMask, decode_mask_to_rle

    h, w, payload = mask["data"].split(",", 2)
    enc = "lossless" if payload.startswith("~") else "one_bit"
    rle = decode_mask_to_rle(SegmentationMask(enc, payload, int(w), int(h)))
    return {"size": list(rle.size), "counts": rle.counts, "x": mask["x"], "y": mask["y"]}


def frame_times_ms(n_frames: int, fps: float) -> list[int]:
    """Instante de cada fotograma; mismo redondeo que ``synth.make_trackset``."""
    step = 1000.0 / fps
    return [round(i * step) for i in range(n_frames)]


def probe_video(path: str) -> dict:
    """Metadatos reales del archivo con ffprobe (ancho, alto, fps exacto, nº de fotogramas)."""
    cmd = ["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames",
           "-show_entries", "stream=width,height,avg_frame_rate,nb_read_frames",
           "-of", "json", path]
    s = json.loads(subprocess.run(cmd, check=True, capture_output=True, text=True).stdout)["streams"][0]
    return {"width": int(s["width"]), "height": int(s["height"]),
            "fps": float(Fraction(s["avg_frame_rate"])), "n_frames": int(s["nb_read_frames"])}


def build_trackset(
    clip_id: str,
    sha256: str,
    video: dict,
    results: list[SamResult],
    *,
    include_masks: bool = False,
    default_score: float = DEFAULT_SCORE,
    model_version: str = "",
) -> TrackSet:
    """Convierte los resultados SAM (uno por prompt) en un ``TrackSet``.

    ``video`` es el dict de ``probe_video``. Cada id de SAM es un tracklet distinto del mismo
    ``prompt_id`` (el motor decide por fotograma la mejor observación). Un resultado sin
    detecciones produce un tracklet vacío con el rango procesado completo: ausencia válida.
    """
    n, fps = video["n_frames"], video["fps"]
    t = frame_times_ms(n, fps)
    clip = ClipMeta(clip_id=clip_id, sha256=sha256, width=video["width"], height=video["height"],
                    analysis_fps=fps, frame_t_ms=t, duration_ms=round(n * 1000.0 / fps))
    tracklets: list[Tracklet] = []
    for res in results:
        by_id: dict[int, list[FrameObs]] = {}
        for d in res.detections:
            if not 0 <= d.frame < n:
                raise SamParseError(f"fotograma {d.frame} fuera de rango (clip de {n})")
            x1, y1, x2, y2 = d.box
            ob = FrameObs(
                f=d.frame, score=d.score if d.score is not None else default_score,
                bbox=(x1 / d.width, y1 / d.height, x2 / d.width, y2 / d.height),
                mask_rle=decode_mask_rle(d.mask) if include_masks and d.mask else None)
            by_id.setdefault(d.object_id, []).append(ob)
        if not by_id:
            tracklets.append(Tracklet(track_id=f"{res.prompt_id}#none", prompt_id=res.prompt_id,
                                      obs=[], processed_frames=(0, n - 1)))
        for oid, obs in sorted(by_id.items()):
            obs.sort(key=lambda o: o.f)
            tracklets.append(Tracklet(track_id=f"{res.prompt_id}#{oid}", prompt_id=res.prompt_id,
                                      obs=obs, processed_frames=(0, n - 1)))
    refs = [r.request_id for r in results if r.request_id]
    return TrackSet(clip=clip, model=ModelRef(model_id="sam-3.1", version=model_version, request_ids=refs),
                    tracklets=tracklets)
