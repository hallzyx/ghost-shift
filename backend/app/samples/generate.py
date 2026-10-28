"""Genera los vídeos de ejemplo (sintéticos: bloques de colores sobre fondo claro).

Uso: python -m app.samples.generate   (reescribe los .mp4 de esta carpeta)
Son clips SINTÉTICOS para probar la app sin grabar; no sustituyen vídeo real.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np

W, H, FPS, DUR, S = 640, 360, 10, 8, 60
BLUE, YEL, SKIN, BG = (30, 60, 220), (240, 210, 20), (224, 172, 140), (235, 235, 230)
OUT = Path(__file__).parent


def _lerp(a, b, t):
    return a + (b - a) * min(max(t, 0), 1)


def render(path: Path, *, a_in=1.0, b_in=4.0, a_side="L", b_side="R", skip_b=False, hand=None, hand_hold=False):
    """A termina en x=160, B en x=480. `hand=(t0,t1)` tapa A con un rectángulo color piel."""
    def block(t_in, side, x_final):
        def pos(t):
            if t < t_in:
                return None
            start = -S if side == "L" else W
            return _lerp(start, x_final, (t - t_in) / 0.8), 150
        return pos
    # el bloque que entra por la izquierda siempre acaba a la izquierda, etc.
    xa, xb = (160 if a_side == "L" else 480), (480 if b_side == "R" else 160)
    objs = [("A", block(a_in, a_side, xa), BLUE)]
    if not skip_b:
        objs.append(("B", block(b_in, b_side, xb), YEL))
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
           "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", "-an", str(path)]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for f in range(FPS * DUR):
        t = f / FPS
        img = np.zeros((H, W, 3), np.uint8)
        img[:] = BG
        for _, pos, col in objs:
            q = pos(t)
            if q:
                x, y = int(round(q[0])), int(q[1])
                x0, x1 = max(x, 0), min(x + S, W)
                if x1 > x0:
                    img[y:y + S, x0:x1] = col
        if hand:
            t0, t1 = hand
            k = min(1.0, max(0.0, (t - (t0 - 0.3)) / 0.3))
            if not hand_hold:
                k = min(k, max(0.0, ((t1 + 0.3) - t) / 0.3))
            if k > 0:
                y = int(_lerp(-120, 125, k))
                img[max(y, 0):y + 110, 135:245] = SKIN
        p.stdin.write(img.tobytes())
    p.stdin.close()
    p.wait()


SCENARIOS = {
    "reference": dict(hand=(6.0, 7.0)),
    "run_ok": dict(a_in=1.4, b_in=4.6),
    "run_wrong_order": dict(a_in=4.0, b_in=1.0),
    "run_missing_b": dict(skip_b=True),
    "run_hand_at_end": dict(hand=(6.0, 8.0), hand_hold=True),
}

if __name__ == "__main__":
    for name, kw in SCENARIOS.items():
        render(OUT / f"{name}.mp4", **kw)
        print("ok", name)
