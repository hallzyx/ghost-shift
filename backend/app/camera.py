"""Registro del encuadre (cámara en mano) con OpenCV, sin red y determinista.

Observa, no decide: estima una homografía por fotograma hacia un fotograma ancla usando rasgos SIFT del
FONDO (la mesa), con las cajas de SAM de objetos y manos enmascaradas, y otra entre clips (ancla de la
ejecución -> ancla de la referencia). Con ellas transforma las cajas de SAM a las coordenadas de la
referencia, donde están definidas las zonas. Lo que no se puede registrar se reporta; el motor decide
(``CalibrationResult``): cámara inestable -> REVIEW global, sin alineación con la referencia -> las reglas
de zona pasan a REVIEW.

Todas las homografías se expresan en coordenadas normalizadas 0–1 de cada clip.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np
from ghostshift_engine.contracts.tracks import FrameObs, TrackSet, Tracklet
from ghostshift_engine.verdict import CalibrationResult

REG_WIDTH = 480  # resolución de trabajo del registro
MIN_TEXTURE_KP = 80  # rasgos de fondo mínimos en el ancla para poder medir la cámara
MIN_INLIERS = 30
MIN_INLIER_RATIO = 0.25
STATIC_SHIFT = 0.012  # desplazamiento máx. (fracción de la diagonal) por debajo del cual la cámara es fija
MAX_UNREGISTERED = 0.20  # fracción de fotogramas sin registro a partir de la cual la cámara es «inestable»
MASK_PAD = 0.15  # margen alrededor de cada caja de SAM excluido del fondo
BORDER = 0.02


@dataclass
class ClipRegistration:
    status: str  # static | compensated | unchecked | unstable
    anchor: int
    H: list[list[float] | None]  # por fotograma: fotograma (norm) -> ancla (norm), 9 floats; None = sin registro
    registered_ratio: float
    max_shift: float
    texture_kp: int
    unregistered: list[int] = field(default_factory=list)
    error: str | None = None

    def summary(self) -> dict:
        return {"status": self.status, "anchor": self.anchor, "registered_ratio": round(self.registered_ratio, 3),
                "max_shift": round(self.max_shift, 3), "texture_kp": self.texture_kp,
                "unregistered": len(self.unregistered), "error": self.error}


def read_frames(path: Path) -> list[np.ndarray]:
    cap = cv2.VideoCapture(str(path))
    out = []
    while True:
        ok, fr = cap.read()
        if not ok:
            break
        h, w = fr.shape[:2]
        g = cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY)
        out.append(cv2.resize(g, (REG_WIDTH, round(h * REG_WIDTH / w)), interpolation=cv2.INTER_AREA))
    cap.release()
    return out


def _boxes_by_frame(ts: TrackSet) -> dict[int, list]:
    out: dict[int, list] = {}
    for tl in ts.tracklets:
        for o in tl.obs:
            out.setdefault(o.f, []).append(o.bbox)
    return out


def _bg_mask(shape, boxes) -> np.ndarray:
    h, w = shape
    m = np.full((h, w), 255, np.uint8)
    for x0, y0, x1, y1 in boxes:
        pw, ph = (x1 - x0) * MASK_PAD, (y1 - y0) * MASK_PAD
        m[max(0, int((y0 - ph) * h)):int(np.ceil((y1 + ph) * h)), max(0, int((x0 - pw) * w)):int(np.ceil((x1 + pw) * w))] = 0
    return m


_SIFT = None


def _features(gray, mask):
    global _SIFT
    if _SIFT is None:
        _SIFT = cv2.SIFT_create(nfeatures=1500)
    kp, des = _SIFT.detectAndCompute(gray, mask)
    return kp, des


def _norm_h(Hpx, src_shape, dst_shape) -> np.ndarray:
    sh, sw = src_shape
    dh, dw = dst_shape
    S_src = np.diag([sw, sh, 1.0])
    S_dst_inv = np.diag([1.0 / dw, 1.0 / dh, 1.0])
    H = S_dst_inv @ Hpx @ S_src
    return H / H[2, 2]


_UNIT_SIGN = float(np.sign(cv2.contourArea(np.float32([[0, 0], [1, 0], [1, 1], [0, 1]]), oriented=True)))


def _sane(H: np.ndarray) -> bool:
    """La homografía (normalizada) debe ser una deformación plausible de una cámara en mano."""
    c = np.array([[0, 0], [1, 0], [1, 1], [0, 1]], np.float64).reshape(-1, 1, 2)
    q = cv2.perspectiveTransform(c, H).reshape(-1, 2)
    # mismo sentido de giro que el cuadrado unidad: sin reflejo (una cámara real no produce imágenes espejo)
    area = cv2.contourArea(q.astype(np.float32), oriented=True) * _UNIT_SIGN
    if not 0.35 <= area <= 2.8 or not cv2.isContourConvex(q.astype(np.float32)):
        return False
    return abs(H[2, 0]) < 1.0 and abs(H[2, 1]) < 1.0


def match(fa, fb, shape_a, shape_b) -> tuple[np.ndarray | None, int]:
    """Homografía (normalizada) a -> b con test de razón + RANSAC. Devuelve (H|None, inliers)."""
    (kpa, da), (kpb, db) = fa, fb
    if da is None or db is None or len(kpa) < 8 or len(kpb) < 8:
        return None, 0
    pairs = cv2.BFMatcher(cv2.NORM_L2).knnMatch(da, db, k=2)
    good = [m for m, *rest in pairs if rest and m.distance < 0.75 * rest[0].distance]
    if len(good) < MIN_INLIERS:
        return None, 0
    pa = np.float32([kpa[m.queryIdx].pt for m in good])
    pb = np.float32([kpb[m.trainIdx].pt for m in good])
    cv2.setRNGSeed(0)  # RANSAC determinista
    Hpx, inl = cv2.findHomography(pa, pb, cv2.RANSAC, 3.0, maxIters=2000, confidence=0.995)
    if Hpx is None:
        return None, 0
    n_in = int(inl.sum())
    if n_in < MIN_INLIERS or n_in / len(good) < MIN_INLIER_RATIO:
        return None, n_in
    H = _norm_h(Hpx, shape_a, shape_b)
    return (H, n_in) if _sane(H) else (None, n_in)


def _shift(H: np.ndarray, aspect: float) -> float:
    """Desplazamiento máximo de las esquinas del fotograma, como fracción de la diagonal."""
    c = np.array([[0, 0], [1, 0], [1, 1], [0, 1]], np.float64).reshape(-1, 1, 2)
    q = cv2.perspectiveTransform(c, H).reshape(-1, 2) - c.reshape(-1, 2)
    q[:, 1] /= aspect  # y en unidades de ancho
    return float(np.max(np.hypot(q[:, 0], q[:, 1])) / np.hypot(1.0, 1.0 / aspect))


def pick_anchor(ts: TrackSet) -> int:
    """Último fotograma sin mano detectada (las zonas se definen al final); si no hay, el último."""
    n = len(ts.clip.frame_t_ms)
    hands = {o.f for tl in ts.tracklets if tl.prompt_id == "aux:hand" for o in tl.obs}
    return next((f for f in range(n - 1, -1, -1) if f not in hands), n - 1)


def register_clip(frames: list[np.ndarray], ts: TrackSet, anchor: int | None = None) -> ClipRegistration:
    n = min(len(frames), len(ts.clip.frame_t_ms))
    anchor = pick_anchor(ts) if anchor is None else anchor
    anchor = min(anchor, n - 1)
    boxes = _boxes_by_frame(ts)
    feats = [_features(frames[f], _bg_mask(frames[f].shape, boxes.get(f, []))) for f in range(n)]
    shape = frames[0].shape
    aspect = shape[1] / shape[0]
    tex = len(feats[anchor][0])
    H: list[np.ndarray | None] = [None] * n
    H[anchor] = np.eye(3)
    if tex < MIN_TEXTURE_KP:
        return ClipRegistration("unchecked", anchor, [None] * n, 0.0, 0.0, tex, [])
    # del ancla hacia fuera: directo al ancla y, si falla, encadenado con el vecino ya registrado
    order = sorted(range(n), key=lambda f: (abs(f - anchor), f))
    for f in order[1:]:
        h, _ = match(feats[f], feats[anchor], shape, shape)
        if h is None:
            nb = f + 1 if f < anchor else f - 1
            if H[nb] is not None:
                hn, _ = match(feats[f], feats[nb], shape, shape)
                if hn is not None:
                    h = H[nb] @ hn
                    h = h / h[2, 2]
                    if not _sane(h):
                        h = None
        H[f] = h
    unreg = [f for f in range(n) if H[f] is None]
    ratio = 1 - len(unreg) / n
    shift = max((_shift(h, aspect) for h in H if h is not None), default=0.0)
    if ratio < 1 - MAX_UNREGISTERED:
        status = "unstable"
    elif shift < STATIC_SHIFT and not unreg:
        status = "static"
    else:
        status = "compensated"
    flat = [None if h is None else [float(v) for v in h.ravel()] for h in H]
    return ClipRegistration(status, anchor, flat, ratio, shift, tex, unreg)


def register_cross(run_frames: list[np.ndarray], run_reg: ClipRegistration, run_ts: TrackSet,
                   ref_anchor: np.ndarray, ref_boxes: list) -> tuple[np.ndarray | None, int]:
    """Homografía ancla de la ejecución -> ancla de la referencia. Prueba el ancla y unos fotogramas finales."""
    boxes = _boxes_by_frame(run_ts)
    fref = _features(ref_anchor, _bg_mask(ref_anchor.shape, ref_boxes))
    n = len(run_reg.H)
    cands = [run_reg.anchor] + [f for f in range(n - 1, max(-1, n - 30), -3)
                                if f != run_reg.anchor and run_reg.H[f] is not None]
    best, best_in = None, 0
    for f in cands[:8]:
        fr = _features(run_frames[f], _bg_mask(run_frames[f].shape, boxes.get(f, [])))
        h, n_in = match(fr, fref, run_frames[f].shape, ref_anchor.shape)
        if h is not None and n_in > best_in:
            to_anchor = np.array(run_reg.H[f]).reshape(3, 3)
            hc = h @ np.linalg.inv(to_anchor)  # ancla -> f -> referencia
            hc = hc / hc[2, 2]
            if _sane(hc):
                best, best_in = hc, n_in
    return best, best_in


def _warp_box(H: np.ndarray, b) -> tuple[float, float, float, float]:
    x0, y0, x1, y1 = b
    c = np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1]], np.float64).reshape(-1, 1, 2)
    q = cv2.perspectiveTransform(c, H).reshape(-1, 2)
    return (float(q[:, 0].min()), float(q[:, 1].min()), float(q[:, 0].max()), float(q[:, 1].max()))


def _touches(b) -> bool:
    return b[0] <= BORDER or b[1] <= BORDER or b[2] >= 1 - BORDER or b[3] >= 1 - BORDER


def apply(ts: TrackSet, H: list[list[float] | None], cross: np.ndarray | None) -> TrackSet:
    """Cajas a coordenadas de la referencia. Fotogramas sin registro se descartan; el contacto con el borde
    se calcula sobre la caja original (salir del plano es un hecho del fotograma, no de la mesa)."""
    out = []
    for tl in ts.tracklets:
        obs = []
        for o in tl.obs:
            h = H[o.f] if o.f < len(H) else None
            if h is None:
                continue
            M = np.array(h).reshape(3, 3)
            if cross is not None:
                M = cross @ M
            obs.append(FrameObs(f=o.f, score=o.score, bbox=_warp_box(M / M[2, 2], o.bbox), mask_rle=None,
                                edge=_touches(o.bbox)))
        out.append(Tracklet(track_id=tl.track_id, prompt_id=tl.prompt_id, obs=obs, processed_frames=tl.processed_frames))
    return ts.model_copy(update={"tracklets": out})


@dataclass
class CameraOutcome:
    tracks: TrackSet  # pistas en coordenadas de la referencia (o las originales si no hubo que tocarlas)
    calibration: CalibrationResult
    info: dict


def calibrate(clip: ClipRegistration, cross: np.ndarray | None, cross_inliers: int, has_ref: bool,
              raw: TrackSet) -> CameraOutcome:
    """Traduce las observaciones del registro al ``CalibrationResult`` que consume el motor."""
    info = {**clip.summary(), "cross_inliers": cross_inliers, "cross_shift": None, "has_reference": has_ref,
            "moved_vs_reference": False}
    if clip.status == "unchecked":
        # sin textura no se mide nada; si la referencia SÍ tenía textura, la escena no coincide con ella
        info["moved_vs_reference"] = has_ref
        return CameraOutcome(raw, CalibrationResult("UNCHECKED", camera_moved=has_ref), info)
    if clip.status == "unstable":
        return CameraOutcome(raw, CalibrationResult("INCOMPATIBLE", issue="CAMERA_UNSTABLE"), info)
    aspect = raw.clip.width / raw.clip.height
    if cross is not None:
        info["cross_shift"] = round(_shift(cross, aspect), 3)
    moved_vs_ref = has_ref and cross is None
    info["moved_vs_reference"] = moved_vs_ref
    need_warp = clip.status == "compensated" or (cross is not None and info["cross_shift"] >= STATIC_SHIFT)
    tracks = apply(raw, clip.H, cross) if need_warp else raw
    status = "RECALIBRATED" if need_warp else "ALIGNED"
    return CameraOutcome(tracks, CalibrationResult(status, camera_moved=moved_vs_ref), info)


def save_anchor(frames: list[np.ndarray], reg: ClipRegistration, path: Path) -> None:
    cv2.imwrite(str(path), frames[reg.anchor])


def load_anchor(path: Path) -> np.ndarray | None:
    if not path or not Path(path).is_file():
        return None
    return cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
