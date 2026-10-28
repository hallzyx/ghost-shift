import json
from pathlib import Path

import pytest

from app.meta.sam_adapter import (
    SamParseError, SamResult, build_trackset, decode_mask_rle, frame_times_ms, parse_deltas, probe_video,
)
from ghostshift_engine import Procedure, Verdict, compile_procedure, verify_run

FIX = Path(__file__).parent / "fixtures" / "sam"
VIDEO = {"width": 640, "height": 360, "fps": 10.0, "n_frames": 80}
GT = json.loads((FIX / "ground_truth.json").read_text())["frames"]


def fx(name) -> dict:
    return json.loads((FIX / f"{name}.json").read_text())


def result(name, prompt_id) -> SamResult:
    d = fx(name)
    return SamResult(prompt_id, parse_deltas(d["deltas"]), d["video_frames_processed"])


def iou(a, b):
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    i = ix * iy
    return i / ((a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - i)


def test_parse_with_confidence_matches_ground_truth():
    dets = parse_deltas(fx("blue_conf")["deltas"])
    assert len(dets) == 56 and {d.object_id for d in dets} == {0}
    assert dets[0].frame == 11 and dets[0].width == 640 and dets[0].height == 360
    assert all(d.score == pytest.approx(0.9024, abs=1e-3) for d in dets)
    ious = [iou(d.box, GT[d.frame]["A"]) for d in dets]
    assert min(ious) > 0.9 and sum(ious) / len(ious) > 0.95


def test_parse_without_confidence_has_no_score():
    assert all(d.score is None for d in parse_deltas(fx("blue_noconf")["deltas"]))


def test_zero_deltas_is_valid_result():
    assert parse_deltas(fx("hand_conf")["deltas"]) == []


def test_missing_frames_are_not_emitted():
    frames = {d.frame for d in parse_deltas(fx("blue_conf")["deltas"])}
    assert 60 not in frames and 30 in frames  # mano tapa A en 60-70


def test_bad_line_raises():
    with pytest.raises(SamParseError):
        parse_deltas(["garbage"])


def test_frame_times_use_real_fps():
    assert frame_times_ms(4, 10.0) == [0, 100, 200, 300]
    assert frame_times_ms(3, 30000 / 1001) == [0, 33, 67]


def test_trackset_normalizes_and_keeps_empty_prompt():
    ts = build_trackset("c", "x", VIDEO, [result("blue_conf", "obj:A"), result("hand_conf", "aux:hand")])
    a = next(t for t in ts.tracklets if t.prompt_id == "obj:A")
    hand = next(t for t in ts.tracklets if t.prompt_id == "aux:hand")
    assert a.obs[0].f == 11 and all(0 <= v <= 1 for o in a.obs for v in o.bbox)
    assert hand.obs == [] and hand.processed_frames == (0, 79)
    assert len(ts.clip.frame_t_ms) == 80 and ts.model.model_id == "sam-3.1"


def test_default_score_when_no_confidence():
    ts = build_trackset("c", "x", VIDEO, [result("blue_noconf", "obj:A")])
    assert {o.score for o in ts.tracklets[0].obs} == {0.9}


def test_frame_out_of_range_rejected():
    with pytest.raises(SamParseError):
        build_trackset("c", "x", {**VIDEO, "n_frames": 20}, [result("blue_conf", "obj:A")])


def test_mask_decoding_lossless_and_one_bit():
    pytest.importorskip("meta_sam_parser")
    for name in ("blue_conf", "blue_onebit"):
        d = parse_deltas(fx(name)["deltas"])[30]
        rle = decode_mask_rle(d.mask)
        assert rle["size"][0] == 60 and rle["counts"]


def test_probe_video_fixture():
    meta = probe_video(str(FIX / "synthetic.mp4"))
    assert meta == {"width": 640, "height": 360, "fps": 10.0, "n_frames": 80}


def _proc(a_zone="left", b_zone="right"):
    box = lambda x0, x1: [(x0, 0.35), (x1, 0.35), (x1, 0.65), (x0, 0.65)]
    return compile_procedure(Procedure(
        procedure_id="synthetic", approved_by_user=True,
        zones=[{"id": "workspace", "role": "workspace", "polygon": [(0.02, 0.1), (0.98, 0.1), (0.98, 0.95), (0.02, 0.95)]},
               {"id": "left", "polygon": box(0.15, 0.40)}, {"id": "right", "polygon": box(0.65, 0.90)}],
        rules=[{"id": "R1", "type": "in_zone_at", "object": "A", "zone": a_zone, "at": "end"},
               {"id": "R2", "type": "in_zone_at", "object": "B", "zone": b_zone, "at": "end"},
               {"id": "R3", "type": "before", "first": "place:A", "second": "place:B"}],
        objects=[{"id": "A", "ref_max_score": 0.9}, {"id": "B", "ref_max_score": 0.9}]))


def _tracks():
    return build_trackset("e2e", "sha", VIDEO, [
        result("blue_conf", "obj:A"), result("yellow_conf", "obj:B"), result("hand_conf", "aux:hand")])


def test_e2e_engine_on_real_sam_output_passes():
    report = verify_run(_proc(), _tracks())
    assert report.verdict is Verdict.PASS, [(r.rule_id, r.verdict, r.reason) for r in report.rules]


def test_e2e_engine_fails_when_zones_swapped():
    report = verify_run(_proc("right", "left"), _tracks())
    assert report.verdict is Verdict.FAIL
