"""Validación, normalización y fotogramas de evidencia (ffmpeg/ffprobe)."""
from __future__ import annotations

import subprocess
from pathlib import Path

from .meta.sam_adapter import probe_video

MAX_BYTES = 200 * 1024 * 1024
MIN_S, MAX_S = 2.0, 120.0
ANALYSIS_FPS = 10
MAX_WIDTH = 960


class VideoError(ValueError):
    """Error accionable para el usuario (español)."""


def normalize(src: Path, dst: Path) -> dict:
    """Valida y recodifica a MP4 H.264 10 fps, ≤960 px, sin audio. Devuelve metadatos del resultado."""
    if src.stat().st_size > MAX_BYTES:
        raise VideoError("El video pesa más de 200 MB. Recórtalo o comprímelo e inténtalo de nuevo.")
    try:
        info = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
             "stream=width,height,duration:format=duration", "-of", "default=nw=1", str(src)],
            capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired as e:
        raise VideoError("No se pudo leer el video (tiempo agotado).") from e
    if info.returncode != 0 or "width=" not in info.stdout:
        raise VideoError("No se pudo leer el archivo como video. Usa MP4 o MOV (H.264).")
    kv = dict(line.split("=", 1) for line in info.stdout.splitlines() if "=" in line)
    dur = float(kv.get("duration") if kv.get("duration", "N/A") != "N/A" else 0)
    if dur < MIN_S:
        raise VideoError(f"El video dura {dur:.1f} s; necesita al menos {MIN_S:.0f} s.")
    if dur > MAX_S:
        raise VideoError(f"El video dura {dur:.0f} s; el máximo en este prototipo es {MAX_S:.0f} s.")
    vf = f"fps={ANALYSIS_FPS},scale='min({MAX_WIDTH},iw)':-2"
    r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-vf", vf, "-an",
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", "-movflags", "+faststart", str(dst)],
                       capture_output=True, text=True, timeout=600)
    if r.returncode != 0:
        raise VideoError("No se pudo procesar el video. Prueba a exportarlo de nuevo como MP4 H.264.")
    meta = probe_video(str(dst))
    meta["duration_ms"] = round(meta["n_frames"] * 1000 / meta["fps"])
    return meta


def evidence_frame(video: Path, t_ms: int, box: tuple[float, float, float, float] | None,
                   width: int, height: int) -> bytes:
    """JPEG del fotograma en t_ms con la caja (normalizada) resaltada."""
    vf = "null"
    if box:
        x0, y0, x1, y1 = box
        vf = (f"drawbox=x={int(x0 * width)}:y={int(y0 * height)}:w={max(2, int((x1 - x0) * width))}:"
              f"h={max(2, int((y1 - y0) * height))}:color=0x0866FF:t=4")
    r = subprocess.run(["ffmpeg", "-loglevel", "error", "-ss", f"{t_ms / 1000:.3f}", "-i", str(video),
                        "-frames:v", "1", "-vf", vf, "-f", "image2", "-c:v", "mjpeg", "-q:v", "3", "pipe:1"],
                       capture_output=True, timeout=60)
    if r.returncode != 0 or not r.stdout:
        raise VideoError("No se pudo extraer el fotograma")
    return r.stdout
