"""Geometría normalizada: polígonos rasterizados y fracción de caja dentro de una zona."""
from __future__ import annotations

import math

import numpy as np

GRID = 128


def polygon_area(poly: list[tuple[float, float]]) -> float:
    s = 0.0
    for i, (x0, y0) in enumerate(poly):
        x1, y1 = poly[(i + 1) % len(poly)]
        s += x0 * y1 - x1 * y0
    return abs(s) / 2.0


def _ccw(a, b, c) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _segments_cross(p1, p2, p3, p4) -> bool:
    return _ccw(p1, p3, p4) * _ccw(p2, p3, p4) < 0 and _ccw(p1, p2, p3) * _ccw(p1, p2, p4) < 0


def polygon_is_simple(poly: list[tuple[float, float]]) -> bool:
    n = len(poly)
    if n < 3:
        return False
    for i in range(n):
        for j in range(i + 1, n):
            if j == i + 1 or (i == 0 and j == n - 1):
                continue
            if _segments_cross(poly[i], poly[(i + 1) % n], poly[j], poly[(j + 1) % n]):
                return False
    return True


def rasterize_polygon(poly: list[tuple[float, float]], n: int = GRID) -> np.ndarray:
    """Máscara (n, n) indexada [y, x]; centros de celda dentro del polígono (par-impar)."""
    c = (np.arange(n) + 0.5) / n
    xs, ys = np.meshgrid(c, c)
    inside = np.zeros((n, n), dtype=bool)
    k = len(poly)
    for i in range(k):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % k]
        if y0 == y1:
            continue
        cond = (y0 > ys) != (y1 > ys)
        xint = x0 + (ys - y0) * (x1 - x0) / (y1 - y0)
        inside ^= cond & (xs < xint)
    return inside


def bbox_fraction_in(grid: np.ndarray, bbox: tuple[float, float, float, float]) -> float:
    """Fracción del área del bbox que cae dentro de la zona rasterizada."""
    n = grid.shape[0]
    c = (np.arange(n) + 0.5) / n
    x0, y0, x1, y1 = bbox
    sx = (c >= x0) & (c <= x1)
    sy = (c >= y0) & (c <= y1)
    if not sx.any():
        sx[min(n - 1, max(0, int((x0 + x1) / 2 * n)))] = True
    if not sy.any():
        sy[min(n - 1, max(0, int((y0 + y1) / 2 * n)))] = True
    return float(grid[np.ix_(sy, sx)].mean())


def bbox_area(b) -> float:
    return max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])


def bbox_intersection(a, b) -> float:
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    return max(0.0, w) * max(0.0, h)


def bbox_center(b) -> tuple[float, float]:
    return ((b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0)


def expand_bbox(b, ratio: float):
    w, h = b[2] - b[0], b[3] - b[1]
    return (b[0] - w * ratio, b[1] - h * ratio, b[2] + w * ratio, b[3] + h * ratio)


def dist_frac_diag(a, b, width: int, height: int) -> float:
    """Distancia entre dos puntos normalizados como fracción de la diagonal en píxeles."""
    return math.hypot((a[0] - b[0]) * width, (a[1] - b[1]) * height) / math.hypot(width, height)


def touches_border(b, margin: float) -> bool:
    return b[0] <= margin or b[1] <= margin or b[2] >= 1 - margin or b[3] >= 1 - margin
