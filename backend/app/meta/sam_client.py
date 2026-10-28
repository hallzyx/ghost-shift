"""Cliente mínimo de SAM 3.1 (POST /v1/responses en streaming). La clave sale del entorno."""
from __future__ import annotations

import base64
import json
import os

import httpx

from .sam_adapter import ModelCallError, SamResult, parse_deltas

BASE_URL = "https://api.meta.ai/v1"


def api_key() -> str:
    key = os.environ.get("META_API_KEY") or os.environ.get("MODEL_API_KEY")
    if not key:
        raise RuntimeError("META_API_KEY (o MODEL_API_KEY) no está definida")
    return key


def segment(video: bytes, prompt: str, prompt_id: str, *, confidence: bool = True,
            mask_encoding: str | None = None, timeout: float = 600.0) -> SamResult:
    """Una petición SAM por concepto. Vídeo MP4/MOV H.264 como data URL."""
    metadata = {}
    if confidence:
        metadata["include_confidence"] = "true"  # cadena, no booleano
    if mask_encoding:
        metadata["mask_encoding"] = mask_encoding
    body = {"model": "sam-3.1", "stream": True, "input": [{"type": "message", "role": "user", "content": [
        {"type": "input_text", "text": prompt},
        {"type": "input_video", "video_url": "data:video/mp4;base64," + base64.b64encode(video).decode()}]}]}
    if metadata:
        body["metadata"] = metadata
    headers = {"Authorization": f"Bearer {api_key()}", "Accept": "text/event-stream"}
    deltas: list[str] = []
    frames = None
    request_id = None
    try:
        with httpx.stream("POST", f"{BASE_URL}/responses", json=body, headers=headers, timeout=timeout) as r:
            if r.status_code != 200:
                r.read()
                raise ModelCallError(f"SAM 3.1 respondió HTTP {r.status_code}.",
                                     retryable=r.status_code in (429, 500, 502, 503, 504))
            request_id = r.headers.get("x-request-id")
            event = None
            for line in r.iter_lines():
                if line.startswith("event:"):
                    event = line[6:].strip()
                elif line.startswith("data:") and line[5:].strip() != "[DONE]":
                    data = json.loads(line[5:])
                    if event == "response.output_text.delta":
                        deltas.append(data["delta"])
                    elif event == "response.completed":
                        frames = (data.get("response", {}).get("usage") or {}).get("video_frames_processed")
    except httpx.HTTPError as e:
        raise ModelCallError("No se pudo contactar con SAM 3.1.", retryable=True) from e
    return SamResult(prompt_id, parse_deltas(deltas), frames, request_id)
