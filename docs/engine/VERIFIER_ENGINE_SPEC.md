# GhostShift — Technical specification of the deterministic event and verdict engine

**Document version:** 0.1 (design draft)
**Scope:** the engine that turns SAM 3.1 tracks + an approved procedure into events, PASS/FAIL/REVIEW verdicts, evidence and an audit log. **Out of scope:** frontend, orchestration and Muse Spark prompts, HTTP calls to SAM (only the contract the adapter must deliver is defined).
**References:** PRD v1.0, §7 (EP-04, EP-05, EP-07), §8, §9, §11, §13, §17.

Conventions: **[DECISION]** = a closed choice for the MVP with its justification; **[ASSUMPTION]** = an unverified fact about external APIs, with a check assigned to the API preflight; `t` is always in milliseconds from the start of the clip; coordinates are always normalized to `[0,1]`.

---

## 0. Design principles

1. **The verdict is a pure function** `verify_run(procedure, tracks, calibration, identity_tracks, params) → RunReport`. Same inputs ⇒ byte-for-byte identical output (except the audit envelope with clock timestamps). No network, no randomness, no LLM on the verdict path (PRD §11).
2. **FAIL requires a positive contradicting observation** (an event or state seen with sufficient quality). Missing data never produces FAIL; it produces REVIEW (PRD §8, EP-07).
3. **A gap never erases a state change**: it turns it into an event with a wide time interval. Thus degrading the observation can only move verdicts toward REVIEW (monotonicity property, §7.4).
4. **Global parameters, never per video or per procedure** in the MVP. This avoids the PRD §13 no-go («fixed values for each video») and the critical hard-coding risk (§17).
5. **Time in ms, space in normalized units**, so that changes in fps or pace do not alter the semantics.

---

## 1. Input contract: SAM 3.1 tracks

### 1.1 Responsibility boundary

[DECISION] An **adapter** outside the engine (`backend/adapters/sam_adapter.py`) translates the raw SAM response into a canonical `TrackSet`. The engine never sees the provider's format. Justification: the SAM 3.1 API was not verified at design time; isolating it lets the engine and its tests move ahead with synthetic tracks and confines a format change to the adapter and its *golden tests* with recorded raw responses.

### 1.2 `TrackSet` schema (pydantic v2, `schema_version = "ghostshift.tracks/1"`)

```python
class ClipMeta(BaseModel):
    clip_id: str                 # session uuid
    sha256: str                  # hash of the video file
    width: int; height: int      # pixels of the analyzed video
    analysis_fps: float          # effective fps of the frames sent/returned
    frame_t_ms: list[int]        # timestamp of each analyzed frame (monotonic)
    duration_ms: int

class FrameObs(BaseModel):       # observation of a tracklet in a frame
    f: int                       # index into frame_t_ms
    score: float                 # [0,1], confidence of the instance in that frame
    bbox: tuple[float,float,float,float]   # x0,y0,x1,y1 normalized
    mask_rle: RLE | None         # COCO RLE (counts, size) at analysis resolution
    # area, centroid and fraction-in-zone are computed by the engine (features.py)

class Tracklet(BaseModel):
    track_id: str                # ONLY valid within this clip
    prompt_id: str               # object/concept it was requested with ("obj:A", "aux:hand")
    obs: list[FrameObs]          # frames WITHOUT an observation = absent from the list
    processed_frames: tuple[int,int]  # range SAM processed (distinguishes "not seen" from "not processed")

class AbsenceProbe(BaseModel):   # result of an explicit re-probe (see §4.4)
    prompt_id: str; frames: list[int]; max_score: float

class TrackSet(BaseModel):
    schema_version: Literal["ghostshift.tracks/1"]
    clip: ClipMeta
    model: ModelRef              # id ("sam-3.1"), returned version, request_ids
    tracklets: list[Tracklet]
    absence_probes: list[AbsenceProbe] = []
    background_keyframes: list[str]  # paths to 3 frames (start/middle/end) for calibration
```

Contract decisions:

- **[DECISION] Gaps are represented by absence in `obs`**, not by empty masks, and `processed_frames` bounds what was actually processed. A frame outside `processed_frames` is *unobserved*; inside it and without a `FrameObs` it is *not detected*. Both are distinct from *visible outside the zone*.
- **[DECISION] IDs do not persist between clips and are not assumed stable within the clip**: an object may arrive fragmented into several tracklets (loss and reacquisition). The tracklet→object grouping is done by `identity.py` (§5).
- **[DECISION] An auxiliary concept `aux:hand` is requested** in the same SAM call. Its masks are used only to mark occlusion (§3.4), never for events. If the API does not support the concept, the engine degrades to the area-drop heuristic (§3.4) and logs it.
- **[DECISION] Target `analysis_fps` = 10.** A human placement lasts 0.5–2 s; 10 fps gives 5–20 frames per placement, enough for the stability window (600 ms = 6 frames) at a 3× lower cost than 30 fps. If SAM imposes its own sampling, the engine accepts it: everything is expressed in ms.

### 1.3 Assumptions about the SAM 3.1 API and preflight checks

| # | [ASSUMPTION] (not verified at https://dev.meta.ai/docs/sam/overview) | Preflight check (10 s clip, 3 objects + hands) | If it fails |
|---|---|---|---|
| S1 | Accepts **text/concept prompts** on video (not only points/boxes) | Request "blue block", "hand"; see whether instances are returned | Prompt by the box of frame 0 taken from the reference via Muse Spark; identity depends more on appearance (§5) |
| S2 | Returns a **mask per instance and per frame** with a stable ID within the clip | Count distinct IDs per object across the clip | If it only returns per frame without tracking: frame-to-frame IoU association in the adapter (greedy, IoU≥0.3) |
| S3 | There is a **score per instance and frame** in `[0,1]` | Histogram of scores with the object visible vs. covered | If the score is per track: use relative area as a quality proxy; recalibrate `score_visible` |
| S4 | **RLE/PNG/polygon** mask format decodable locally | Decode and overlay 5 frames | The adapter converts to RLE; if only bbox, `mask_rle=None` (the engine uses the bbox, §3.1) |
| S5 | **Frame index ↔ timestamp** mapping recoverable; controllable sampling fps | Compare the number of returned frames with the duration | Resample on the client (ffmpeg) to 10 fps and send frames or re-encoded video |
| S6 | Duration/size/latency limits compatible with 20–60 s clips | Measure latency and maximum accepted size | Trim/compress; the product limit = the measured one |
| S7 | A hidden object produces **absence or a low score**, not a hallucinated mask elsewhere | Cover an object with a hand for 2 s | Raise `score_visible`; enable the impossible-spatial-jump rule (§3.5) |
| S8 | Identifiable model version and reproducible output | Two identical calls; compare | Cache the `TrackSet` by `sha256` of the video + prompts; the engine re-runs over the cache |
| S9 | A prompt can return **several instances** | Two objects of the same color | Duplicate resolution in §5.2 |

All raw responses from the preflight are saved in `engine/tests/fixtures/sam_raw/` and turned into adapter tests.

---

## 2. Procedure and rule schema (`ghostshift.procedure/2`)

### 2.1 Schema

```json
{
  "schema_version": "ghostshift.procedure/2",
  "procedure_id": "kit-001",
  "version": 3,
  "parent_version": 2,
  "approved_by_user": true,
  "approved_at": "2026-10-30T15:02:11-05:00",
  "content_hash": "sha256:…",
  "scene": {
    "reference_clip_sha256": "…",
    "frame_aspect": 1.7778,
    "background_fingerprint": {"keyframe": "ref_bg.png", "orb_keypoints": 412}
  },
  "objects": [
    {"id": "A", "description": "blue component", "confirmed_by_user": true,
     "signature": {"hsv_hist": [/* 8x4x4 normalized */], "area_norm": 0.012, "aspect": 1.4},
     "ref_keyframes": [{"f": 87, "mask_rle": {"…": "…"}}],
     "indistinguishable_from": []}
  ],
  "zones": [
    {"id": "workspace", "role": "workspace", "polygon": [[0.05,0.10],[0.95,0.10],[0.95,0.95],[0.05,0.95]]},
    {"id": "left", "label": "left zone", "role": "target", "source": "auto",
     "polygon": [[0.12,0.40],[0.30,0.40],[0.30,0.62],[0.12,0.62]]}
  ],
  "rules": [
    {"id": "R1", "type": "in_zone_at", "object": "A", "zone": "left", "at": "end",
     "enabled": true, "origin": "proposed", "text_es": "El componente azul debe estar en la zona izquierda al finalizar"},
    {"id": "R2", "type": "in_zone_at", "object": "A", "zone": "left", "at": "during",
     "from": "place:A", "to": "end", "enabled": false, "origin": "proposed",
     "text_es": "Una vez colocado, el componente azul no debe salir de la zona izquierda"},
    {"id": "R3", "type": "before", "first": "place:A", "second": "place:B",
     "enabled": true, "origin": "user", "text_es": "A debe colocarse antes que B"},
    {"id": "R4", "type": "present_in_zone", "object": "C", "zone": "workspace",
     "enabled": true, "origin": "proposed", "text_es": "El componente C debe aparecer en la mesa"}
  ]
}
```

### 2.2 Type semantics

| Type | Fields | True when… |
|---|---|---|
| `present_in_zone` | `object`, `zone` (default `workspace`) | There is a run of VISIBLE frames ≥ `presence_min_ms` with the object inside the zone (presence per PRD §8) |
| `in_zone_at` + `at:"end"` | `object`, `zone` | In the final window the object is VISIBLE and inside the zone (§4.3) |
| `in_zone_at` + `at:"during"` | `object`, `zone`, `from` (event ref.), `to` (`"end"` or event ref.) | The object stays in the zone throughout the interval, with no observed `remove` event |
| `before` | `first`, `second`: `place:<obj>` or `place:<obj>@<zone>`; `occurrence` (default `"both_agree"`) | The `first` event ends before `second` starts (intervals, §4.5) |

- [DECISION] `place:X` **without a zone** means «X moved and came to rest» anywhere in the `workspace` (§3.2), not «X entered its target zone». Justification: PRD §9 requires «correct order, object outside the zone ⇒ position FAIL, not order»; if `place:B` depended on the correct zone, placing B wrongly would also cause an order FAIL. The `place:X@Z` variant exists for procedures where order only matters inside a zone.
- [DECISION] **v1→v2 migration:** the PRD example `{"type":"present_in_zone", …, "at":"end"}` is automatically migrated to `in_zone_at` with `at:"end"`; `present_in_zone` without `at` keeps its presence meaning. The migration is recorded in the audit log.
- **Zone roles:** `workspace` (exactly one; the valid area of the table), `target` (rule zones), `staging` (optional, origin of the pieces; informational only).

### 2.3 Validation at compile time (`compile_procedure`)

Rejection (actionable error for Rule Studio): `approved_by_user=false`; references to nonexistent objects/zones; a `before` graph with cycles (impossible topological order); `first == second`; a non-simple polygon or area < 0.002; no enabled rule. Warning (does not block): two `target` zones with IoU > 0.3; objects with a non-empty `indistinguishable_from` (§5.3); a `before` rule on objects with no position rule (the `EVENT_NOT_OCCURRED` will stay in REVIEW, §4.5).

Each edit produces `version+1` with `parent_version` and a new `content_hash`; `RunReport`s store `(procedure_id, version, content_hash)` and are never relabeled (PRD §9 «later edits»). `CompiledProcedure` is a `dataclass(frozen=True)` with polygons already rasterized per resolution.

### 2.4 Zone definition

[DECISION] `target` zones are **derived automatically from the reference**: the bbox of the object's mask at its stable final rest, enlarged by `max(30 % of its size, 0.03)` per side and clipped to the `workspace`; Muse Spark only proposes the label («left zone»). The `workspace` is the convex hull of all rest positions observed in the reference, enlarged by 0.05. Justification: it is deterministic, auditable and does not require a zone editor (P1). The user can change the label or disable the rule; geometric editing is left for P1.

### 2.5 Normalization under framing changes and camera incompatibility

Zones live in normalized coordinates **of the reference frame**. For each run, `calibration.py` estimates `T_ref→exec` and transforms the **polygons** (not the tracks):

1. Background: median of the 3 `background_keyframes`, reduced to 320 px wide in grayscale, with objects and hands masked (masks from the `TrackSet` itself).
2. ORB (500 points) + `estimateAffinePartial2D` RANSAC (4-DOF similarity: translation, rotation, uniform scale) between the reference and run backgrounds.
3. Fallback if `inliers < 25` or `inlier_ratio < 0.4` (textureless table): phase correlation (translation only) + NCC of the aligned background.

| Result | Condition | Effect |
|---|---|---|
| `ALIGNED` | translation ≤ 0.03·diag, rot ≤ 2°, scale ∈ [0.97, 1.03] | Applies T silently |
| `RECALIBRATED` | translation ≤ 0.10·diag, rot ≤ 5°, scale ∈ [0.90, 1.10] | Applies T; visible notice in the report |
| `INCOMPATIBLE` | outside the above, or a different aspect ratio (> 1 %), or fallback with NCC < 0.6 | Rules are not evaluated; global REVIEW with `CAMERA_INCOMPATIBLE` and a «recalibrate/re-record» message (PRD §9) |

**Intra-clip motion:** T is estimated between the background of the first and the last second. If translation > 0.02·diag or rot > 1.5° ⇒ `CAMERA_MOVED`: all zone-dependent rules go to REVIEW. Justification: with a fixed camera (P0 requirement) it is cheap (2 estimates per clip, < 100 ms), and any larger drift invalidates the zones faster than we can correct it reliably.

[DECISION] `calibration.py` is the only module that depends on OpenCV (`opencv-python-headless`), and its result enters `verify_run` as data (`CalibrationResult`). The core (events/rules/verdict) is tested without images.

**Implemented (after testing a real handheld video) — supersedes the above where they differ.** The first real video (handheld camera, ~14 % of the diagonal in shift) showed that «fixed camera or REVIEW» makes almost any phone recording unusable. It was implemented in `backend/app/camera.py` (the only module with OpenCV; the engine still has no images):
1. Per frame: SIFT (1500 points, 480 px wide, grayscale) over the **background** — SAM boxes of objects and hands masked with a 15 % margin —, ratio test 0.75 and RANSAC **homography** (the table is a plane) to an **anchor** frame (the last one without a hand). If direct registration fails, it chains with the neighboring frame already registered. Sanity checks: ≥ 30 inliers and ≥ 25 %, convex quadrilateral, area 0.35–2.8 and **no reflection**.
2. Across clips: the run's anchor → the reference's anchor (saved when the reference is analyzed).
3. The **boxes** (not the polygons) are transformed to the reference anchor's coordinates; contact with the edge is computed on the original box (`FrameObs.edge`). Frames without registration are discarded.

| Observation | `CalibrationResult` | Effect on the engine |
|---|---|---|
| shift < 0.012·diag and everything registered | `ALIGNED` | none |
| it moved, ≥ 80 % of frames registered | `RECALIBRATED` | boxes compensated; notice in the report |
| < 80 % registered | `INCOMPATIBLE`, `issue=CAMERA_UNSTABLE` | global REVIEW |
| clip registered but not alignable with the reference | `camera_moved=True` | zone rules REVIEW `CAMERA_MOVED`; `before` and `stacked_on` are evaluated |
| textureless background (< 80 features in the anchor) | `UNCHECKED` (+ `camera_moved` if the reference did have texture) | decided as before and a notice is shown |

---

## 3. `place:X` and `remove:X` event detector

### 3.1 Per-frame features (`features.py`)

For each already-resolved object (§5) and each analyzed frame `f`:

- `area`, `centroid`, `bbox` (from the mask; if `mask_rle=None`, from the bbox).
- `inside[z] = |mask ∩ zone z| / |mask|` with the zone rasterized at the mask's resolution. [DECISION] Area fraction instead of «centroid inside»: it tolerates large objects near the edge and gives a continuous value for hysteresis.
- `hand_overlap = |object_bbox ∩ hand_mask| / |object_bbox|`.
- **Observation state** (`obs_state`):
  - `VISIBLE`: score ≥ `score_visible` and `area ≥ frag_ratio · area_ref` and `hand_overlap < hand_occl`.
  - `OCCLUDED`: detected but with a low score, fragmented area or a hand on top.
  - `ABSENT`: processed and not detected.
  - `UNOBSERVED`: outside `processed_frames`.
  `area_ref` = median area over frames with score ≥ 0.7 of the clip itself (robust to camera scale).

Only `VISIBLE` frames count as positive or contradicting evidence. `OCCLUDED/ABSENT/UNOBSERVED` are **gaps**.

### 3.2 State machine per object

Generic rest events, later annotated with the zone:

```
states: UNKNOWN_INIT → RESTING(pos) ⇄ MOVING → CANDIDATE(pos) → RESTING(pos')
                         ↘ GAP (gap) ↗

for each VISIBLE frame:
  v = centroid displacement over the stable_ms window
  if state ∈ {RESTING} and |centroid − rest_pos| > still_eps:   → MOVING (t_move_lo = last VISIBLE at rest)
  if state ∈ {MOVING, CANDIDATE}:
      if v ≤ still_eps for ≥ stable_ms of VISIBLE frames:
          if dist(new_pos, previous_rest_pos) ≥ move_min or the object entered from outside the workspace:
              emit place(X, zone=argmax_z inside[z] if ≥ θ_in, else None,
                         t_lo = t_move_lo, t_hi = t_start_of_stable_window)
          → RESTING(new_pos)       # if there was not enough displacement: adjustment, not an event
  zone hysteresis in RESTING: current_zone changes to None only if inside < θ_out for ≥ exit_ms VISIBLE
      → emit remove(X, zone, t_lo, t_hi)
```

- **Initial state:** the first stable VISIBLE run sets `RESTING(pos0)` **without an event** and is marked `initial_rest = {pos0, zone}`. An object that is already in its zone from the first frame never generates `place` ⇒ the basis of the «only the end is visible» case (§4.6).
- **Entry from outside the frame:** if the first VISIBLE run starts touching the `workspace` edge and stabilizes inside, `place` is emitted with `t_lo` = first visible frame (the object was *brought in*).
- **Event interval:** `[t_lo, t_hi]` brackets the placement instant with certainty: before `t_lo` it was somewhere else (seen), from `t_hi` it is still at the new place (seen). The instant shown to the user is `t_hi` (the first stable evidence frame) and the key frame is the one with the highest score in the stable window.

### 3.3 Parameters (global, frozen `EngineParams`, with a hash in the audit log)

| Parameter | Default | Reason |
|---|---|---|
| `analysis_fps` | 10 | §1.2 |
| `score_visible` | 0.50 | [ASSUMPTION S3]; recalibrate with the preflight histogram |
| `frag_ratio` | 0.55 | A hand covering ~half leaves the object as OCCLUDED |
| `hand_occl` | 0.15 | Hand/bbox overlap above which the position is not reliable |
| `θ_in` / `θ_out` | 0.60 / 0.35 | Hysteresis: avoids flicker at the zone edge |
| `stable_ms` | 600 | Minimum persistence (PRD §8); > duration of grasp pauses (~300 ms) |
| `still_eps` | 0.010 · diag | Expected SAM centroid noise < 0.5 % |
| `move_min` | 0.05 · diag | Distinguishes a real placement from a readjustment |
| `exit_ms` | 300 | Confirmed exit from the zone |
| `max_gap_ms` | 1000 | Bridge for short gaps (a hand passing) |
| `end_window_ms` | 1000 | Final-state window |
| `end_visible_ratio` | 0.70 | Minimum coverage in the final window |
| `presence_min_ms` | 500 | Sustained presence |
| `coverage_min` | 0.90 | Coverage required to assert «the event did not occur» |

All temporal thresholds are converted to frames with `ceil(ms · fps / 1000)`. [DECISION] There are no per-procedure overrides in the MVP (principle 4); a change of defaults is an engine version change and forces re-evaluating the 12 runs (§7.5).

### 3.4 Occlusion by hands

1. If there is an `aux:hand` mask: frames with `hand_overlap ≥ hand_occl` ⇒ OCCLUDED.
2. If there is none (S1 fails): OCCLUDED if `area < frag_ratio · area_ref` or the score drops > 0.3 relative to the 1 s moving median.
3. During OCCLUDED the machine **neither advances nor resets**: it does not count for the stability window or for `exit_ms`. Intended consequence: the placement is dated when the hand withdraws and the object is still and visible, which is what is actually observable.

### 3.5 Gaps (absent detection)

When a gap `[g0, g1]` ends and the object returns to VISIBLE:

- If `g1 − g0 ≤ max_gap_ms` **and** `dist(pos_before, pos_after) ≤ still_eps·3` ⇒ bridge: continue as if there had been no gap.
- If the position changed ≥ `move_min` (or the gap is long and the position changed) ⇒ **event with a wide interval**: `place` with `t_lo = g0` (last visible at the previous place), `t_hi` = start of the new stable window, and `timing_uncertain = true`. It is never discarded (principle 3).
- If the position did not change but the gap > `max_gap_ms` ⇒ a `gap` is recorded with no event; `during` rules covering the gap cannot be TRUE (§4.4).
- **Impossible jump:** if the object appears > 0.25·diag from its last position in < 200 ms with no hand nearby, it is treated as a possible instance confusion: the run is marked `identity_suspect` and its events carry that mark (⇒ REVIEW in rules that use them).

### 3.6 Restarts and multiple placements

- Each `place` carries an ordinal per object (`k = 1, 2, …`). A readjustment < `move_min` is not a placement.
- Two canonical occurrences are defined per object: **first** (`k=1`) and **definitive** (the last `place` after which the object does not move ≥ `move_min` again until the end).
- [DECISION] `before` uses `occurrence:"both_agree"` by default: it is evaluated with both occurrences; if they agree, that is the result; if they disagree ⇒ REVIEW with `ORDER_AMBIGUOUS_REPLACEMENT` and both pairs of evidence. Justification: «A, B, readjust A» and «B, remove B, A, B (correction)» have opposite normative readings that a human operator decides better; the PRD §13 deliberate-error dataset does not include corrections, so the cost in FAIL recall is zero there. `occurrence:"first"` and `"definitive"` remain available in the schema for the user to set in Rule Studio.

---

## 4. Verdict logic

### 4.1 Three-valued semantics

Each evaluator returns `Outcome(value ∈ {TRUE, FALSE, UNKNOWN}, reason_code, evidence[], missing[])` with the mapping TRUE→PASS, FALSE→FAIL, UNKNOWN→REVIEW. Internal combinations use strong Kleene logic (`AND(FALSE, UNKNOWN)=FALSE`, `AND(TRUE, UNKNOWN)=UNKNOWN`).

**Preconditions** (applied before the evaluator; any of them forces UNKNOWN for the affected rules):

| Gate | Scope | Reason |
|---|---|---|
| `INSUFFICIENT_OBSERVATION` | global: no object with ≥ `presence_min_ms` VISIBLE | PRD §9 «no detectable objects»; EP-07 |
| `CAMERA_INCOMPATIBLE` / `CAMERA_MOVED` | global / rules with a zone | §2.5 |
| `IDENTITY_UNCONFIRMED` | rules that mention an ambiguous object | §5 |
| `IDENTITY_SUSPECT` | rules that use a flagged event | §3.5 |

### 4.2 The golden rule of FAIL

[DECISION] An evaluator may only return FALSE if it attaches at least one `Evidence` of type `event` or `state` built with VISIBLE frames (or a confirmed `AbsenceProbe`, §4.4). The aggregator checks this and downgrades to UNKNOWN (`INTERNAL_NO_EVIDENCE`, logged as a bug) if it is not met. This implements EP-05 («a FAIL contains… an event that contradicts it») as an invariant, not as a convention.

### 4.3 `in_zone_at` (`at: end`)

Window `W` = the last `end_window_ms` analyzed. `V` = VISIBLE frames of `W`.

1. `|V|/|W| < end_visible_ratio`:
   - if the object observably left the `workspace` (last VISIBLE touching the edge with outward velocity) ⇒ FALSE `OBJECT_REMOVED`;
   - if there is no detection at all in the clip and the absence is confirmed (§4.4) ⇒ FALSE `OBJECT_NOT_FOUND`;
   - otherwise ⇒ UNKNOWN `NOT_VISIBLE_AT_END` (includes hands covering: PRD §9).
2. Median of `inside[zone]` over `V` ≥ θ_in ⇒ TRUE.
3. Median ≤ θ_out ⇒ FALSE `OUT_OF_ZONE`, with evidence of the key frame and the zone it is in (if any).
4. In between ⇒ UNKNOWN `BORDERLINE_POSITION`.

`at: during` over `[t(from), t(to)]` (with `t` = `t_hi` of the events): FALSE if there is an observed `remove` from that zone in the interval; TRUE if VISIBLE coverage ≥ 0.8, all gaps bridged and median inside ≥ θ_in; UNKNOWN otherwise (including the `from` event not having occurred: `ANCHOR_EVENT_MISSING`).

### 4.4 `present_in_zone` and absence

TRUE if there is a VISIBLE run ≥ `presence_min_ms` with inside ≥ θ_in. For FALSE, **confirmed absence** is required: (a) the global segmentation is not empty (other objects are seen), (b) the calibration is `ALIGNED/RECALIBRATED`, (c) the zone is not occluded by hands in the final window, and (d) the adapter ran an `AbsenceProbe` (re-probe of the same prompt over the 5 final frames) with `max_score < 0.3`, when that same prompt detected the object in the reference with score ≥ 0.7. If any is missing ⇒ UNKNOWN `ABSENCE_UNCONFIRMED`. Justification: the PRD requires both detecting «an object is missing» (a typical error) and not producing a FAIL from empty segmentation; condition (a)+(d) separates «SAM does not work on this clip» from «the object is not there».

### 4.5 `before` (precedence by intervals)

```python
def eval_before(ev1: Event|None, ev2: Event|None, ctx) -> Outcome:
    if ev1 and ev2:
        if ev1.t_hi < ev2.t_lo:  return TRUE(evidence=[ev1, ev2])
        if ev2.t_hi < ev1.t_lo:  return FALSE("ORDER_VIOLATED", evidence=[ev2, ev1])
        return UNKNOWN("ORDER_OVERLAP", missing=["time separation between placements"])
    if ev2 and not ev1:
        # B was placed; was A observed without being placed until t_lo(B)?
        if ctx.only_initial_rest(A) and ctx.visible_coverage(A, 0, ev2.t_lo) >= coverage_min:
            return FALSE("FIRST_EVENT_MISSING_BEFORE_SECOND", evidence=[ev2, state(A at ev2.t_lo)])
        return UNKNOWN("ORDER_NOT_OBSERVED")
    if ev1 and not ev2:
        return UNKNOWN("EVENT_NOT_OCCURRED")       # the omission is judged by the position rules
    return UNKNOWN("ORDER_NOT_OBSERVED")          # neither observed
```

- [DECISION] Order is decided by **strict separation of intervals**, not by comparing point instants. Simultaneous placements (two hands) or ones with overlapping gaps ⇒ REVIEW. This makes the rule monotonic with respect to frame loss.
- [DECISION] If the second event does not occur, `before` stays REVIEW and not FAIL: no event contradicts the order, and the absence of B is reported by its position rule (cause isolation, PRD §9). If the procedure has no position rule for B, the compiler already warned about it (§2.3).

### 4.6 Global aggregation

```
if a global gate is active           → REVIEW (with blocking_issue; UI: «no verdict»)
if ∃ enabled rule FAIL               → FAIL
if ∃ enabled rule REVIEW             → REVIEW
if all PASS and n_enabled ≥ 1        → PASS
```

Disabled rules are reported as `SKIPPED` and do not participate. FAIL > REVIEW precedence (EP-05) is safe because a FAIL can never depend on an object with unconfirmed identity (gate §4.1).

### 4.7 Table of edge cases (PRD §9 and additional)

| Case | Typical observation | Result per rule | Global |
|---|---|---|---|
| Video without detectable objects | No tracklet with ≥ 500 ms VISIBLE | All REVIEW `INSUFFICIENT_OBSERVATION` | REVIEW «no verdict», recommend re-recording |
| Hands cover an object at the end | `|V|/|W|` < 0.7 due to `hand_overlap` | `in_zone_at end` REVIEW `NOT_VISIBLE_AT_END`; `before` may still be decided | REVIEW (unless another FAIL) |
| Same components, wrong order | place:B.t_hi < place:A.t_lo | `in_zone_at` PASS ×N; `before` FAIL `ORDER_VIOLATED` | FAIL |
| Correct order, object outside the zone | place:B in zone None/other, after A | `before` PASS; `in_zone_at(B)` FAIL `OUT_OF_ZONE` | FAIL |
| Two nearly identical objects | assignment margin < δ (§5) | Rules of both REVIEW `IDENTITY_UNCONFIRMED` until human confirmation | REVIEW → re-evaluation after confirming |
| Only the end is visible | All in `initial_rest` inside a zone; 0 `place` events | `in_zone_at end` PASS; `before` REVIEW `ORDER_NOT_OBSERVED` | REVIEW |
| Strong camera change | Calibration `INCOMPATIBLE` | Not evaluated | REVIEW `CAMERA_INCOMPATIBLE`, ask for recalibration |
| Camera moved mid-clip | Drift > 0.02·diag | Zone rules REVIEW `CAMERA_MOVED` | REVIEW |
| Simultaneous placement of A and B | Overlapping intervals | `before` REVIEW `ORDER_OVERLAP` | REVIEW |
| A placed, B, A readjusted (≥ move_min) | first: A<B; definitive: B<A | `before` REVIEW `ORDER_AMBIGUOUS_REPLACEMENT` | REVIEW |
| Object missing altogether | No detection, probe < 0.3, others visible | `present_in_zone`/`in_zone_at` FAIL `OBJECT_NOT_FOUND` | FAIL |
| Empty segmentation due to model failure | No object detected | (= first row) | REVIEW, never PASS/FAIL |
| Object removed from the table at the end | Leaves through the edge, visible | `in_zone_at end` FAIL `OBJECT_REMOVED` | FAIL |
| Later rule edit | New `version` | Previous reports keep their `(version, hash)` | — |
| Unapproved procedure | `approved_by_user=false` | Rejected at compile time | Not run |
| Tower covered by the hand at the end | < 50 % of the final window with both objects usable | `stacked_on` REVIEW `STACK_NOT_VISIBLE_AT_END` | REVIEW |
| Two prompts mark the same piece | IoU ≥ 0.8 between distinct objects | `IDENTITY_CONFLICT` | REVIEW |

### 4.8 `stacked_on` (vertical order at the end) and identity between similar objects

`{"type":"stacked_on","object":"C","base":"A"}`: «C» ends up **directly on top of** «A» at the end. Compilation: both exist and are distinct, an object has at most one base, no cycles. A tower of N pieces = N−1 rules.

Evaluation in the final window (`end_window_ms`), per frame with both objects usable (VISIBLE, or OCCLUDED only due to a reduced box **with no hand on top**: in a tower the bottom piece only shows its side):
- horizontal overlap / width of the narrower one < 0.30 ⇒ `APART`;
- overlap ≥ `stack_overlap_min` (0.60) and rise `(cy_base − cy_top)/min(height)` ≥ `stack_rise_min` (0.25) and gap `(y0_base − y1_top)/max(height)` ≤ `stack_gap_max` (0.50) ⇒ `ON`; symmetric ⇒ `UNDER`; with a larger gap ⇒ `APART`; otherwise `UNCLEAR`.
- ≥ 70 % `ON` ⇒ PASS `STACKED`; ≥ 70 % `UNDER` ⇒ FAIL `STACK_INVERTED`; ≥ 70 % `APART` ⇒ FAIL `NOT_STACKED`; otherwise REVIEW `STACK_UNCLEAR`. With < 50 % of the window usable ⇒ REVIEW (`STACK_NOT_VISIBLE_AT_END` or `IDENTITY_CONFLICT`). Evidence: key frame of both objects with the count.

Limitation: with a single oblique camera, «behind» can look like «on top of» (same projection). It is not resolved; it is documented.

**Per-frame identity** (`features.resolve_identities`): SAM returns all the instances that match the concept (real: «green tape roll» marked all 3 rolls). Order: (1) an object with a single candidate fixes it; (2) from one with several, those that coincide (IoU ≥ `dup_iou`) with another object's fixed box are removed; (3) if several remain, continuity of the SAM tracking id relative to the nearest resolved frame; (4) otherwise `AMBIGUOUS` (neither visible nor absent); (5) two objects with the same box ⇒ both `AMBIGUOUS`.

---

## 5. Identity matching across clips

### 5.1 Strategy

1. **Prompts per confirmed object.** On the run, SAM receives one prompt per object with the confirmed `description` (and aliases proposed by Muse Spark). Each tracklet arrives with `prompt_id` (S1). This already separates most cases of distinguishable objects.
2. **Intra-clip grouping:** tracklets with the same `prompt_id` that do not overlap in time and whose union is spatially continuous (end→start ≤ `max_gap_ms` and ≤ 0.1·diag, or the next one starts at the edge) are merged into an *object track*. Overlapping tracklets of the same prompt with score ≥ 0.5 ⇒ **competing candidates** (S9).
3. **Assignment cost** object `o` ↔ candidate track `p` (everything in `[0,1]`):
   `c = 0.35·(1 − prompt_match) + 0.40·d_Bhattacharyya(hsv_o, hsv_p) + 0.15·min(1, |ln(area_p/area_o)|/ln 2) + 0.10·min(1, |ln(aspect_p/aspect_o)|/ln 2)`
   with `prompt_match = 1` if the track came from `o`'s prompt, `0` otherwise. HSV signatures are computed over masked pixels in VISIBLE frames with score ≥ 0.7.
4. **Optimal assignment** by permutation enumeration (≤ 4 objects ⇒ ≤ 24 assignments; no SciPy).
5. **Muse Spark as a signal, not a judge.** Only if there is ambiguity (5.2), the orchestrator may ask Muse Spark to match crops with descriptions; its answer enters as a cached, logged `IdentityHint(source="muse", mapping, confidence)`. The engine uses it to **order** the options shown to the human, never to close an ambiguity by itself. Justification: PRD §8 requires confirmation if the match is ambiguous and §11 forbids delegating the verdict to the LLM; a wrong identity generates false FAILs.

[DECISION] **The final position (zone) is not used as an identity signal.** The PRD mentions «zone verification», but using it to assign identity is circular: it would favor each object being «in its zone» and would hide precisely the «A in B's zone» error. The zone is only used *afterwards*, as a coherence check: if two objects with close signatures (d < 0.25) appear swapped relative to the reference, the assignment is marked ambiguous.

### 5.2 Ambiguity thresholds

| Condition | State | Effect |
|---|---|---|
| Best-assignment cost for `o` ≤ 0.45 and margin over the second-best global assignment ≥ 0.15 | `AUTO_CONFIRMED` | Rules are evaluated |
| Margin < 0.15, or cost > 0.45, or unresolved competing candidates, or suspected swap (§5.1) | `NEEDS_CONFIRMATION` | The object's rules REVIEW `IDENTITY_UNCONFIRMED`; `RunReport.identity_requests` lists candidate crops |
| No candidate with cost ≤ 0.7 | `NOT_FOUND` | Treated as a candidate absence (§4.4) |

Human confirmation enters as `IdentityHint(source="user")`, which fixes the assignment; `verify_run` is re-run (cheap: no model calls) and the report records who confirmed.

### 5.3 Indistinguishable objects in the reference

At compile time, if two objects have `d_Bhattacharyya < 0.20` and an area ratio ∈ [0.8, 1.25], they are marked `indistinguishable_from` and Rule Studio asks for a differentiating description. If the user accepts anyway, every run will ask for identity confirmation for that pair (PRD §9 «two nearly identical objects»).

---

## 6. Evidence and audit log

### 6.1 `RunReport` (`ghostshift.report/1`)

```python
class Evidence(BaseModel):
    kind: Literal["event", "state", "absence", "gap", "calibration"]
    object_id: str | None; zone_id: str | None
    track_ids: list[str]                 # tracklets of the run clip
    t_ms: int                            # instant shown (t_hi for events)
    t_interval_ms: tuple[int, int] | None
    frames: list[int]                    # frames that support the claim
    keyframe: int                        # frame to highlight in the UI
    mask_rle: RLE | None; bbox: tuple[float,float,float,float] | None
    zone_polygon_exec: list[tuple[float,float]] | None   # zone already transformed
    metrics: dict[str, float]            # inside, score, visible_ratio, hand_overlap…
    flags: list[str]                     # timing_uncertain, identity_suspect…

class RuleResult(BaseModel):
    rule_id: str; rule_text_es: str
    verdict: Literal["PASS", "FAIL", "REVIEW", "SKIPPED"]
    reason_code: str                     # closed enumeration (§4)
    explanation_es: str                  # deterministic template per reason_code
    evidence: list[Evidence]; missing: list[str]   # which data was missing (REVIEW)

class RunReport(BaseModel):
    schema_version: Literal["ghostshift.report/1"]
    run_id: str; global_verdict: Literal["PASS", "FAIL", "REVIEW"]
    blocking_issue: str | None
    procedure_ref: ProcedureRef          # id, version, content_hash
    rules: list[RuleResult]
    events: list[Event]                  # full timeline (including unused events)
    identity: IdentityResolution; calibration: CalibrationResult
    identity_requests: list[IdentityRequest]
    provenance: Provenance               # see 6.2
```

[DECISION] The Spanish explanations come from **templates per `reason_code`** («B was placed at t=4.2 s, before A (t=7.9 s)»), not from an LLM. Muse Spark may rephrase them in the UI, but the canonical text is the template's.

### 6.2 Audit

- **Append-only JSONL** file per session (`audit/<session>.jsonl`), one line per fact: `procedure_compiled`, `model_call` (model, version, `request_id`, latency, `cache_hit`, prompt hash), `trackset_ingested` (sha256), `calibration`, `identity_resolved` (source: auto/user/muse), `verdict`.
- `Provenance` in each report: `engine_version` (semver + git sha), `params_hash`, `procedure.content_hash`, `trackset_sha256`, `video_sha256`, `identity_hints_hash`.
- **Replay:** `ghostshift-engine replay <run_id>` rebuilds the report from the cached `TrackSet` and compares the hash; any difference is a determinism failure. This is the proof, for any reviewer, that no per-video results are precomputed (PRD §4.2, §15).
- Privacy (PRD §12): the log stores hashes and metadata, not frames; evidence crops live with the session and are deleted with it.

---

## 7. Testing strategy

### 7.1 Tools

`pytest` + `hypothesis` (property tests). No engine test calls models or the network; an import test fails if `ghostshift_engine` imports `requests`, `httpx`, `urllib3` or `socket`.

### 7.2 Synthetic track generator (`synth.py`)

A scenario DSL → `TrackSet` + ground truth:

```python
Scenario(
  fps=10, duration_ms=20000, size=(160, 90),
  objects={"A": Rect(w=.06, h=.05, start=(.15, .80)), "B": Rect(w=.05, h=.05, start=(.30, .80))},
  zones=std_zones("left", "right"),
  actions=[Move("A", to="left", t0=3000, dur=1200), Move("B", to="right", t0=7000, dur=1000)],
  occlusions=[Hand(over="A", t0=18500, t1=20000)],     # also generates the aux:hand track
  dropouts=[Dropout("B", t0=7200, t1=7800)],
  noise=Noise(centroid_sigma=.003, score_mu=.85, score_sigma=.05, id_switch_prob=.0),
  camera=Shift(dx=.0, dy=.0, rot_deg=0),
  start_ms=0,                                          # >0 simulates «only the end is visible»
).render() -> (TrackSet, GroundTruth(events=[…], expected={"R1": "PASS", …}))
```

Masks are rasterized as rectangles/ellipses at low resolution and encoded in RLE, to exercise the full `features → events → rules` path. Movements use trajectories with lift-off (apparent scale and a hand on top) to simulate grasps. `id_switch_prob` fragments tracklets to test grouping.

### 7.3 Unit tests (per module)

- `geometry`: RLE round trip; `inside` of known rectangles; polygon transformation.
- `events`: a clean placement ⇒ 1 `place` with `t_hi − t_real ∈ [stable_ms, stable_ms+100]`; readjustment < `move_min` ⇒ 0 events; hysteresis at the edge (inside oscillating 0.5↔0.55) ⇒ 0 `remove`; short gap at rest ⇒ bridge; gap with displacement ⇒ `timing_uncertain` event; entry from outside the frame.
- `rules`/`verdict`: one test per row of the §4.7 table, built with `synth.py`.
- `identity`: 3 objects of distinct colors with shuffled IDs ⇒ correct assignment; two objects with the same signature ⇒ `NEEDS_CONFIRMATION`; zone swap with similar signatures ⇒ ambiguous.
- `contracts`: v1→v2 migration of the literal PRD §8 example; rejection of cycles in `before`.
- `adapter` (outside the engine): golden tests with `fixtures/sam_raw/` from the preflight.

### 7.4 Invariant properties (hypothesis over random valid scenarios)

| ID | Property |
|---|---|
| P1 | **Never PASS or FAIL with empty segmentation**: a `TrackSet` without object tracklets ⇒ global REVIEW and all rules REVIEW |
| P2 | **REVIEW monotonicity**: adding gaps/occlusions or lowering scores can only change PASS→REVIEW or FAIL→REVIEW; never PASS↔FAIL |
| P3 | Every FAIL has ≥ 1 `Evidence` with non-empty `frames` and VISIBLE frames |
| P4 | Invariance to permutation/renaming of `track_id` |
| P5 | Invariance to pace: scaling action times ×[0.6, 1.8] (keeping pauses ≥ `stable_ms`) does not change verdicts |
| P6 | Invariance to fps: the same scenario at 8, 10 and 15 fps produces the same verdicts |
| P7 | Camera shift within `ALIGNED` with calibration applied ⇒ same verdicts |
| P8 | Determinism: two runs ⇒ identical `RunReport` (hash) |
| P9 | Disabling a rule does not change the verdict of the others |
| P10 | Aggregation: global == the §4.6 function over the per-rule verdicts |
| P11 | «Same final state, different order»: for every pair of scenarios that differ only in the order of `Move`, the `in_zone_at end` rules coincide and at least one `before` differs |

P2 is the most delicate; if hypothesis finds a counterexample, the detector is fixed (the property is not relaxed).

### 7.5 Evaluation of the 12-run dataset (PRD §13)

1. **Before running anything**, `dataset/manifest.yaml` is written: per clip, procedure, type (correct / error type X / insufficient), expected overall verdict, expected per-rule verdict and hand-annotated placement instants (±200 ms). It is versioned in git (a commit before the first evaluation).
2. Recommended distribution of the 6 errors (3 per procedure): reversed order with the same final state (≥ 1 per procedure, PRD §13), object in the wrong zone, missing object, two objects swapped between zones, object removed at the end. Insufficient (2): hands over the zone at the end; a recording that starts after the placements.
3. `TrackSet`s are cached after the single SAM call; `ghostshift-engine eval dataset/` runs offline and emits: a 3×3 global matrix (expected × obtained), a per-rule matrix, temporal error of events (median and p90), recall/precision of `place` events, and `params_hash`.
4. **Anti-overfitting rule:** any parameter change after seeing results is recorded with a reason, changes `params_hash` and forces re-evaluating all 12; the second procedure cannot motivate parameter changes (it is the generalization set). The results of the first evaluation and of the final one are both reported honestly.
5. Success criterion (PRD §13): 4/4 PASS, ≥ 5/6 FAIL with the correct causing rule, 2/2 REVIEW, **0 FAIL on correct or insufficient clips** (an additional, stricter requirement: a false FAIL is worse than a REVIEW), temporal error p90 ≤ 500 ms on events used as evidence.

---

## 8. Engine structure

[DECISION] **Plain Python 3.11**, `pydantic` v2 for contracts (validation + JSON Schema export for the frontend), `numpy` for masks, `opencv-python-headless` only in `calibration.py`. No SciPy, no network. Justification: the backend and the model SDKs will most likely be Python; numpy covers RLE and rasterization; the problem size (≤ 4 objects, ≤ 600 frames) does not require more performance (target: `verify_run` < 1 s per 60 s clip).

```
engine/
  pyproject.toml
  ghostshift_engine/
    __init__.py          # public API: compile_procedure, propose_from_reference, verify_run
    version.py
    contracts/
      tracks.py          # TrackSet, Tracklet, FrameObs, AbsenceProbe
      procedure.py       # schema v2, v1→v2 migration, validation
      params.py          # EngineParams (frozen) + defaults + hash
      results.py         # Event, Evidence, RuleResult, RunReport, reason codes
    geometry.py          # RLE, polygon rasterization, inside, transformations
    calibration.py       # T_ref→exec, intra-clip drift (OpenCV)
    features.py          # per-frame features and obs_state
    identity.py          # tracklet grouping, costs, assignment, ambiguity
    events.py            # place/remove state machine, gaps, occurrences
    rules.py             # type registry → evaluator (adding a type = adding a function)
    verdict.py           # gates, Kleene, aggregation, golden rule of FAIL
    explain.py           # es-ES templates per reason_code
    audit.py             # JSONL, provenance, replay
    synth.py             # scenario generator (also used by tests)
    cli.py               # verify | replay | eval
  tests/{unit,property,fixtures}/
```

`propose_from_reference(trackset_ref)` reuses `features` + `events` over the reference clip to produce zones (§2.4) and the observed `place` chain; the orchestrator cross-checks it with the Muse Spark proposal and marks as a **hypothesis** any order proposed by the LLM that contradicts the observed events (EP-02).

---

## 9. Residual risks and no-go criteria

### 9.1 Residual risks

| Risk | Why it persists | Mitigation in this design |
|---|---|---|
| SAM does not offer temporal tracking or text prompts in the API | Not verified (S1, S2) | Adapter with IoU association and box prompts; the engine does not change |
| Event date biased by the hand | Stability is measured after the hand withdraws | Dated with an interval `[t_lo, t_hi]`; order uses interval separation |
| Short sliding placements (< `move_min`) | Indistinguishable from a readjustment | Recording guide; `move_min` measured with real clips |
| Objects stacked or occluded by each other | Out of scope (P2), but will appear | `frag_ratio` ⇒ OCCLUDED ⇒ REVIEW, not FAIL |
| Too much REVIEW («timid» product) | Conservative decisions (§3.6, §4.5) | Measure the REVIEW rate on correct clips; target 0/4 |
| Derived zones too strict | A single reference | 30 % margin; `BORDERLINE_POSITION` ⇒ REVIEW instead of FAIL |
| Color signatures sensitive to lighting | Unnormalized HSV | Histogram with coarse V (4 bins); human confirmation as a safety net |

### 9.2 Measurable go / no-go criteria

Measured over ≥ 3 real pairs (reference + run) with hand-annotated instants:

| Stage | Metric | Go | No-go / action |
|---|---|---|---|
| Observation | SAM API returns per-frame masks with intra-clip identity (or associable by IoU) at ≥ 5 effective fps | Yes | **No-go of the sequence engine** if there is no usable temporal output ⇒ rethink (PRD §13) |
| Observation | VISIBLE coverage of objects in hand-free stretches | ≥ 85 % | < 70 % ⇒ change framing/lighting before continuing |
| Observation | Placement recall (event with `t_hi` within 500 ms of the annotated one) | ≥ 90 % | < 75 % ⇒ PRD **conditional go**: presence/position only, do not sell order |
| Observation | False placements per clip | ≤ 0.5 on average | > 1 ⇒ same as the previous row |
| Identity | Correct automatic identity (`AUTO_CONFIRMED` and correct) | ≥ 90 % of objects | < 70 % ⇒ human confirmation mandatory on every run (acceptable for early use, declared) |
| Identity | `AUTO_CONFIRMED` **incorrect** identity | 0 | > 0 ⇒ raise margin δ to 0.25 and re-measure; if it persists, always confirm |
| Engine | Synthetic suite: §7.3 tests + properties P1–P11 | 100 % green | Any failure in P1/P2/P3 blocks integration with the UI |
| Engine | Correct verdict on the 3 real pairs without changing parameters between clips | 3/3 (REVIEW accepted on the insufficient one) | A false FAIL on a correct clip ⇒ do not advance without diagnosing |
| Performance | SAM latency per 30 s clip | ≤ 3 min | > 5 min ⇒ drop to 5 fps and clips ≤ 20 s (global parameter, re-measure P6) |

If placement recall does not reach the threshold, the product is presented as a **state** verifier (presence and position) and the `before` rule is hidden in Rule Studio, without describing GhostShift as a sequence verifier (PRD §13, §14).
