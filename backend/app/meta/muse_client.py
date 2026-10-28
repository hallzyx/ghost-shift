"""Muse Spark 1.3 (modo Standard, NUNCA -contributor): propone objetos, zonas y eventos.

La salida es una PROPUESTA: el motor y SAM la contrastan; el usuario la aprueba.
"""
from __future__ import annotations

import base64
import json

import httpx

from .sam_adapter import ModelCallError
from .sam_client import BASE_URL, api_key

MODEL = "muse-spark-1.3"  # nunca "-contributor": permite entrenar con el contenido enviado

SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["objects", "zones", "events", "uncertainties"],
    "properties": {
        "objects": {"type": "array", "items": {"type": "object", "additionalProperties": False,
            "required": ["id", "label_es", "sam_prompt"],
            "properties": {"id": {"type": "string"}, "label_es": {"type": "string"}, "sam_prompt": {"type": "string"}}}},
        "zones": {"type": "array", "items": {"type": "object", "additionalProperties": False,
            "required": ["label_es", "bbox"],
            "properties": {"label_es": {"type": "string"},
                           "bbox": {"type": "array", "items": {"type": "number"}, "minItems": 4, "maxItems": 4}}}},
        "events": {"type": "array", "items": {"type": "object", "additionalProperties": False,
            "required": ["type", "object", "zone_label_es", "t_seconds"],
            "properties": {"type": {"type": "string", "enum": ["place"]}, "object": {"type": "string"},
                           "zone_label_es": {"type": "string"}, "t_seconds": {"type": "number"}}}},
        "uncertainties": {"type": "array", "items": {"type": "string"}},
    },
}

PROMPT = (
    "Analiza este video de cámara fija sobre una mesa donde una persona realiza un procedimiento colocando objetos. "
    "Devuelve JSON con: objects (los 2-4 objetos relevantes en orden de aparición; id 'A','B',...; label_es = nombre corto en "
    "español como 'Cuadrado azul'; sam_prompt = frase de 2-3 palabras EN INGLÉS con color y forma, p. ej. 'blue square', para "
    "un modelo de segmentación), zones (zonas de destino donde terminan los objetos; label_es en español; bbox normalizado "
    "[x0,y0,x1,y1] entre 0 y 1), events (cuando un objeto se coloca y queda quieto en una zona: type 'place', object id, "
    "zone_label_es, t_seconds), uncertainties (dudas en español: objetos poco visibles, ambiguos, tapados). "
    "No incluyas manos ni brazos como objetos. Solo lo que realmente se ve; no inventes.")


def propose(video: bytes, timeout: float = 300.0) -> tuple[dict, dict]:
    """Devuelve (propuesta, info_llamada{request_id, model, status})."""
    body = {"model": MODEL, "input": [{"type": "message", "role": "user", "content": [
        {"type": "input_text", "text": PROMPT},
        {"type": "input_video", "video_url": "data:video/mp4;base64," + base64.b64encode(video).decode()}]}],
        "text": {"format": {"type": "json_schema", "name": "reference_analysis", "schema": SCHEMA, "strict": True}}}
    try:
        r = httpx.post(f"{BASE_URL}/responses", json=body, timeout=timeout,
                       headers={"Authorization": f"Bearer {api_key()}"})
    except httpx.HTTPError as e:
        raise ModelCallError("No se pudo contactar con Muse Spark.", retryable=True) from e
    if r.status_code != 200:
        raise ModelCallError(f"Muse Spark respondió HTTP {r.status_code}.", retryable=r.status_code in (429, 500, 502, 503, 504))
    j = r.json()
    text = "".join(c.get("text", "") for o in j.get("output", []) if o.get("type") == "message" for c in o.get("content", []))
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ModelCallError("Muse Spark devolvió una respuesta no válida.", retryable=True) from e
    return data, {"request_id": r.headers.get("x-request-id"), "model": j.get("model", MODEL), "status": "ok"}
