"""Registro de cámara con movimientos conocidos sobre una textura sintética (verdad de terreno exacta)."""
import cv2
import numpy as np

from app import camera
from ghostshift_engine.contracts.tracks import ClipMeta, FrameObs, TrackSet, Tracklet

W, H = 480, 360


def texture(seed=0):
    rng = np.random.default_rng(seed)
    big = cv2.GaussianBlur(rng.integers(0, 255, (H * 2, W * 2)).astype(np.uint8), (0, 0), 2.0)
    return cv2.equalizeHist(big)


def shot(tex, dx, dy, zoom=1.0):
    """Encuadre de la «mesa» desplazado (dx, dy px) y con zoom: lo que vería una cámara en mano."""
    cx, cy = tex.shape[1] / 2 + dx, tex.shape[0] / 2 + dy
    M = np.float32([[zoom, 0, W / 2 - zoom * cx], [0, zoom, H / 2 - zoom * cy]])
    return cv2.warpAffine(tex, M, (W, H))


def trackset(n, obj_boxes=None):
    obs = [FrameObs(f=f, score=0.9, bbox=b) for f, b in enumerate(obj_boxes or [])]
    return TrackSet(clip=ClipMeta(clip_id="t", width=W, height=H, analysis_fps=10,
                                  frame_t_ms=[i * 100 for i in range(n)], duration_ms=n * 100),
                    tracklets=[Tracklet(track_id="a", prompt_id="obj:A", obs=obs, processed_frames=(0, n - 1))])


def test_static_camera_is_left_untouched():
    tex = texture()
    frames = [shot(tex, 0, 0)] * 10
    reg = camera.register_clip(frames, trackset(10))
    assert reg.status == "static"
    out = camera.calibrate(reg, None, 0, False, trackset(10))
    assert out.calibration.status == "ALIGNED"


def test_pan_and_zoom_are_compensated_so_a_fixed_point_stays_fixed():
    tex = texture()
    moves = [(4 * i, -3 * i, 1.0 + 0.01 * i) for i in range(15)]
    frames = [shot(tex, dx, dy, z) for dx, dy, z in moves]
    # un objeto pegado a la mesa en el punto (cx+20, cy+10) de la textura: su caja en cada fotograma
    boxes = []
    for dx, dy, z in moves:
        px, py = W / 2 + z * (20 - dx), H / 2 + z * (10 - dy)
        boxes.append(((px - 15) / W, (py - 15) / H, (px + 15) / W, (py + 15) / H))
    ts = trackset(15, boxes)
    reg = camera.register_clip(frames, ts)
    assert reg.status == "compensated" and reg.registered_ratio == 1.0
    out = camera.calibrate(reg, None, 0, False, ts)
    assert out.calibration.status == "RECALIBRATED"
    centers = np.array([((o.bbox[0] + o.bbox[2]) / 2 * W, (o.bbox[1] + o.bbox[3]) / 2 * H)
                        for o in out.tracks.tracklets[0].obs])
    assert np.ptp(centers, axis=0).max() < 1.5  # px: el objeto deja de «moverse»
    assert all(o.edge is False for o in out.tracks.tracklets[0].obs)


def test_unregistrable_frames_make_the_camera_unstable():
    tex = texture()
    frames = [shot(tex, 3 * i, 0) for i in range(10)] + [texture(seed=100 + i)[:H, :W] for i in range(10)]
    reg = camera.register_clip(frames, trackset(20))
    assert reg.status == "unstable" and reg.registered_ratio <= 0.8
    out = camera.calibrate(reg, None, 0, True, trackset(20))
    assert out.calibration.status == "INCOMPATIBLE" and out.calibration.issue == "CAMERA_UNSTABLE"


def test_textureless_background_is_unchecked_and_mismatch_if_reference_had_texture():
    flat = [np.full((H, W), 200, np.uint8)] * 5
    reg = camera.register_clip(flat, trackset(5))
    assert reg.status == "unchecked"
    assert camera.calibrate(reg, None, 0, False, trackset(5)).calibration.camera_moved is False
    assert camera.calibrate(reg, None, 0, True, trackset(5)).calibration.camera_moved is True


def test_cross_clip_registration_and_mirror_rejected():
    tex = texture()
    ref = shot(tex, 0, 0)
    run_frames = [shot(tex, 40, 25, 1.1)] * 3
    ts = trackset(3)
    reg = camera.register_clip(run_frames, ts)
    Hc, n_in = camera.register_cross(run_frames, reg, ts, ref, [])
    assert Hc is not None and n_in >= camera.MIN_INLIERS
    mirrored = [cv2.flip(f, 0) for f in run_frames]
    reg_m = camera.register_clip(mirrored, ts)
    assert camera.register_cross(mirrored, reg_m, ts, ref, [])[0] is None
