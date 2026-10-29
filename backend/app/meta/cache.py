"""Caché en disco de respuestas crudas de modelos (sha256 del video + petición).

Las llamadas a Muse/SAM cuestan y SAM es reproducible a nivel de caja (docs/meta-findings.md S8):
repetir la misma petición sobre el mismo video devuelve la respuesta grabada. Los ficheros tienen el
mismo formato que las fixtures de pruebas (``deltas`` + ``video_frames_processed``), así que una
respuesta real cacheada puede copiarse tal cual como fixture. ``GHOSTSHIFT_MODEL_CACHE=""`` la desactiva.
Nunca se guarda la clave de la API ni las cabeceras.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path


def _dir() -> Path | None:
    d = os.getenv("GHOSTSHIFT_MODEL_CACHE", "data/model_cache")
    return Path(d) if d else None


def key(kind: str, video: bytes, **params) -> str:
    blob = json.dumps({"kind": kind, "video": hashlib.sha256(video).hexdigest(), **params}, sort_keys=True)
    return f"{kind}_{hashlib.sha256(blob.encode()).hexdigest()[:24]}"


def get(k: str) -> dict | None:
    d = _dir()
    if d is None or not (d / f"{k}.json").is_file():
        return None
    try:
        return json.loads((d / f"{k}.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def put(k: str, value: dict) -> None:
    d = _dir()
    if d is None:
        return
    d.mkdir(parents=True, exist_ok=True)
    tmp = d / f"{k}.json.tmp"
    tmp.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    tmp.replace(d / f"{k}.json")
