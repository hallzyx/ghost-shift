# Meta API findings

Verified with real calls on **October 28, 2026** over a **synthetic** video (2 blocks, 640×360, 10 fps, 8 s; generator and ground truth in `backend/tests/fixtures/sam/`). Legend: ✅ verified with a real call · ❌ fails / not met · 📄 documentation only · ⏳ untested. **Limit of the evidence:** a single synthetic clip with flat blocks; no real hands, variable lighting or moving camera.

## Access
- `GET /v1/models` with `Authorization: Bearer <key>` → 200. Models listed: `sam-3.1`, `muse-spark-1.3`, `muse-spark-1.3-contributor`, `muse-spark-1.2(-contributor)`, `muse-spark-1.1`, `muse-wonder-1.0`, `muse-image-1.0`, `muse-voice-transcribe-1.0`. ✅
- Environment variable: the environment exposes `META_API_KEY`; the official docs use `MODEL_API_KEY`. The client accepts both. ✅
- **Do not use** `muse-spark-1.3-contributor` (Meta may train on the content; incompatible with PRD §12). It was not called. ✅

## SAM 3.1 (`POST /v1/responses`, streaming)
Body: `input=[{type:message, role:user, content:[{input_text: "<concept>"},{input_video: video_url}]}]`, `stream:true`, `metadata:{include_confidence:"true"}` (string). The text arrives in `response.output_text.delta` events, one per frame; it ends with `response.completed` (with `usage.video_frames_processed`) and a `[DONE]`.

| # | Status | Real evidence |
|---|---|---|
| S1 | ✅ | "blue square" → only A (56 frames, 1 id); "yellow square" → only B (38). Color filters well. One request per concept. |
| S2 | ✅ (limited) | A single id (0) per request for the whole clip, even after occlusion (A reappears with the same id). With a simple clip an id change could not be forced; the adapter still treats each id as a separate tracklet. |
| S3 | ✅ / ❌ | With `include_confidence`, `c` arrives on box and mask. **But `c` was constant per object** (A=0.9024 across all 56 frames, B=0.9064), not per frame as the docs say. **It does not drop under occlusion**, so the engine cannot rely on the score to detect occlusion: it must use absence/area/overlap with `aux:hand` (spec §3.4). Without the option there is no `c`; the adapter uses 0.9 by default. |
| S4 | ✅ | Format exactly as documented. Box in source pixels with `w,h`. Mask = **crop of the box** at its own resolution (`x=0;y=0` are offsets inside the crop), fill ≈1.0 on squares. Custom base85 alphabet (ASCII 33–123 without `" , ; < > \ |`) and `~` is a context-based range codec, not trivial: the official `meta-sam-parser` 0.0.6 (SAM License) is used as an optional dependency for masks. |
| S5 | ✅ | `<Nf>` indices are 0-based and match the file's frames (A starts at 11 = first frame with 27 px visible per ground truth). Frames without an object emit no line. `video_frames_processed`=80 = actual frames in the file. |
| S6 | ✅ (partial) | A base64 data URL accepts 7.7 KB (80 frames) and 37 KB (**1280×720, 240 frames, 24 s**: 12.9 s total). Latency for the 8 s clip: TTFB 0.9–2.0 s, **total 3.9–5.1 s**. Documented limit 📄: MP4/MOV (H.264/H.265/MPEG-4), up to 15,000 frames, 16 objects per frame. Long/heavy clips, the data URL size limit and `file_id` with SAM untested. |
| S7 | ✅ (with caveats) | With block A **fully covered** (frames 60–70) SAM returned **absence** (no line), not hallucinated masks. With partial occlusion (58–59, 71–72) it returns the box of the visible piece. Defects: 2 frames with a visible object and no detection (57, 73) → the engine must tolerate short gaps. **"hand" returned 0 results** on my "hand" (a skin-colored rectangle); **`aux:hand` stays ⏳ until tested with real hands.** |
| S8 | ✅ (approx.) | Two identical calls: **identical boxes** in 56/56 frames, but **the masks differ in bytes** on every line. With vs. without `include_confidence`: 1 of 56 boxes differs by 1 px. Reproducible at box level, not bit for bit ⇒ keep a cache by sha256 of the video + prompt and do not require bit-for-bit equality. No finer model version than `model: sam-3.1` is returned. |
| S9 | ✅ | All instances of the concept per request (here 1 per clip; multiple not tested). |
| Accuracy | ✅ | Mean IoU against ground truth: A 0.969 (min 0.918), B 0.967 (min 0.959); 0 false positives. |
| Cost | ✅ | `usage.video_frames_processed` = 80 per request (minimum billable 50); 📄 $0.20 / 1000 frames. |
| `one_bit` | ✅ | `metadata.mask_encoding:"one_bit"` works and reduces the text from 37 KB to 8 KB (same boxes). Recommended if masks are stored. |

### Design consequences
1. One SAM request per object plus one `aux:hand`, in parallel (5 calls for 4 objects). The 3 in the e2e test took ~4 s each.
2. **Do not use `c` to decide occlusion**; use absence, area drop and overlap with the hand. Adjust spec §3.1 if the constant score is confirmed on real video.
3. Zero deltas = a valid result (absence), not an error (tests with `hand_conf`).
4. `frame_t_ms` is computed with the real fps (ffprobe) and the real `n_frames`; SAM processes every frame in the file. ✅ **Resampling tested**: a 1280×720 30 fps video is normalized in the backend to 960×540 at 10 fps; SAM and the engine give the same instants (A 1.8 s, B 4.8 s) as with the original at 10 fps.
5. ❌ **SAM does not understand Spanish prompts** ("cuadrado azul", "bloque azul", "mano" → 0 results). Each object stores a Spanish name for the user and a short English `sam_prompt` (proposed by Muse and editable by the user).

## Muse Spark 1.3 (Standard mode) — `text.format` json_schema, strict
Tested with the same video, uploaded through the Files API (`POST /v1/files`, `purpose=user_data`, 200, `file-…`) and through `input_video` (data URL). Both routes work. Schema: objects / zones (normalized bbox) / events (`enter|place|remove|occlusion`, `t_seconds`).

| Aspect | Status | Result |
|---|---|---|
| Valid JSON per schema | ✅ | 2/2 valid responses (with `strict:true`). |
| Objects | ✅ / ❌ | Run 1 (file): A blue, B yellow and an **invented object "C"** (the hand, "peach square"). Run 2 (video): only A and B. |
| Zones | ✅ | Z1≈[0.24–0.33 × 0.41–0.59] and Z2≈[0.75–0.84 × 0.43–0.58] in run 2 (real: A 0.25–0.34 × 0.42–0.58; B 0.75–0.84 × 0.42–0.58). Run 1 looser but correct. |
| `enter/place` instants | ✅ (±0.5 s) | enter A 1.0 s (real 1.0); place A 2.1 (real ≈1.8); enter B 4.2 (real 4.0); place B 5.2 (real ≈4.8). Identical in both runs. |
| Occlusion | ❌ | Said 5.2 s and 6.3/7.3 s; real 5.7–7.3 s (hand). Inconsistent textual evidence ("muted purple"). |
| Reproducibility | ❌ | Two runs gave different results (object C, number of events). |
| Latency / cost | ✅ | 15–28 s per 8 s clip; ~2.2 k input tokens and 3–5 k output (almost all reasoning). |

**Conclusion:** useful for *proposing* objects, zones and approximate order (reference phase), with the structure guaranteed by the schema; **not reliable for deciding exact times, nor occlusion, nor as a source of the verdict**. Proposals must go in as `proposed|hypothesis` and be validated by the user/SAM, as the design already provides. What was measured applies only to this synthetic clip.

## End-to-end verification (real calls)
`backend/app/meta/sam_client.py` → 3 real requests (`obj:A`, `obj:B`, `aux:hand`) → `sam_adapter.build_trackset` → `verify_run`: **PASS** (R1 IN_ZONE, R2 IN_ZONE, R3 ORDER_OK). The same result is reproduced offline in `backend/tests/test_sam_adapter.py` with recorded raw responses, and with the zones swapped the engine gives **FAIL**.

## First REAL video (October 28, 2026): handheld camera, 3 stacked tape rolls
Phone video 1280×960, 9.8 s, ~24 fps (normalized to 960×720, 10 fps, 99 frames). Three rolls of adhesive tape (blue, green, beige) in a row on a floral tablecloth; a hand picks up the blue one and puts it on the green one, then the beige on top (tower: green, blue, beige). One reference + 6 runs through the app (real backend on :8000), 1 Muse call and 4 SAM calls per clip (3 objects + `hand`); repeats reuse the cache of recorded responses.

**Muse Spark 1.3** (1 real call): 3 correct objects («Cinta azul» `blue tape roll`, «Cinta verde» `green tape roll`, «Cinta marrón» `brown tape roll`), 1 reasonable zone and two placements (blue 4.5 s, beige 7.8 s; real ≈4.5 and ≈7.8). It warned on its own that blue and green look alike and that the green one ends up almost covered. It cannot express stacking (its schema only has `place`).

**SAM 3.1** ✅ **real hands**: `hand` detected the hand in 75/99 frames, but with a **huge box** (hand + arm, e.g. 670×430 px of 960×720) that overlaps everything underneath ⇒ the engine marks as covered objects that are only nearby. It is conservative (more REVIEW, never a false PASS).
❌ **multiple instances**: «green tape roll» returned **all 3 rolls** (3 ids, in all 99 frames, constant scores 0.96 green / 0.95 beige / 0.89 blue). «blue tape roll» and «brown tape roll» returned only their own. In the reversed video, «blue tape roll» added a 2nd instance (the green one) from the middle onward. Choosing «the one with the highest score» was right by chance ⇒ the engine now resolves identities (discards candidates that are another object's box, uses SAM id continuity and, if still in doubt, flags `IDENTITY_CONFLICT` → REVIEW).
✅ ids stable for the whole clip (no id change with the hand on top). `c` is still constant per instance (confirmed on real video).
⚠️ the bottom piece of a tower only shows its side: its box shrinks to ~45 % of the area it had alone, which the «fragment» rule (`frag_ratio`) interprets as occlusion.

**Handheld camera** (SIFT registration + homography over the tablecloth, SAM boxes masked): 99/99 frames registered, maximum shift **13.8 % of the diagonal**, ~5 s of CPU per clip. A still roll «moves» 37 px in the original video and 3 px after compensation. The patterned tablecloth gives 500–700 background features per frame; on the synthetic videos (plain background) there is no texture and the status is `UNCHECKED`.

| Clip (how it was obtained) | Camera | Verdict | Why |
|---|---|---|---|
| same video | RECALIBRATED (13.8 %) | **PASS** | 3× IN_ZONE; blue on green and beige on blue STACKED in 11/11 final frames |
| trimmed to 0–5.7 s (beige still beside) | RECALIBRATED | **REVIEW** | the hand box covers the tower at the end: NOT_VISIBLE / STACK_NOT_VISIBLE_AT_END. Ideally it would be FAIL on «beige on blue»; the engine does not decide without seeing |
| reversed in time (ends in a row = «scattered») | RECALIBRATED (17 % + 12 % vs. ref.) | **FAIL** | NOT_STACKED on both (overlap 2–3 %); note: «blue in zone» gives PASS, so **without the stacking rule this case would not fail** |
| 72 % crop with sinusoidal pan (shakier) | RECALIBRATED (41.8 %, 97 % registered, 22.8 % vs. ref.) | **PASS** | same as the original |
| fast pan + blur 2.5–7.5 s | INCOMPATIBLE (48 % registered) | **REVIEW** | global `CAMERA_UNSTABLE`, nothing is decided |
| flipped vertically (upside-down tower; artificial) | not alignable with the reference (a mirror is not a camera motion) | **FAIL** | STACK_INVERTED on both; zone rules REVIEW `CAMERA_MOVED` |

With the same tracks but **without compensating the camera**, the same video gives REVIEW («blue in zone» `NOT_VISIBLE_AT_END`) and the shakier one REVIEW (plus `BORDERLINE_POSITION` for the beige); the stacking rules give the same with or without compensation (they are relative). **Note, small margin:** the PASS of «blue in zone» depends on the fragment rule: the final box of the blue roll (the middle piece, half covered by the beige) measures 0.60–0.65 of its median area with compensation and 0.47–0.52 without it, against a threshold of 0.55. For zone rules on pieces covered by the tower the result is fragile; the stacking rule admits reduced boxes with no hand on top. **There is no real recording with a different stacking order**: the vertical flip is a manipulation, not a physical run; the blur and the pan are also simulated with ffmpeg.

**Temporal order (`before`) with real hands**: the event detector placed the blue roll's «placement» between 1.3 and 5.8 s and the beige's between 2.7 and 8.8 s (the hand moves the boxes long before releasing) ⇒ overlapping intervals ⇒ `ORDER_OVERLAP` (REVIEW) on the same video. In a tower the order is already required by the stacking, so no `before` is proposed between pieces of the same tower.

## Pending / not verified
- More real videos: another stacking order actually recorded, other tables (plain = no texture to register against), other lighting, more objects.
- Hand masks instead of its box (the box covers too much); it has not been tested whether the `hand` masks are tighter.
- «Behind» versus «on top of» with a single oblique camera (same projection): unresolved.
- Maximum data URL size / `file_id` with SAM; 30–60 s clips; rate limits (📄 see `pricing-rate-limits`).
- Variable-frame-rate (VFR) video.

## Full app flow with real calls (October 28, 2026)
Backend running + a sample reference video → Muse proposes 2 objects (in Spanish, with an English `sam_prompt`) → SAM (3 parallel requests) → proposed rules (zones from each object's final position; instants 1.8 s and 4.8 s = ground truth) → approval → 4 sample runs, all with the expected verdict:

| Sample | Verdict | Reason |
|---|---|---|
| `run_ok` | PASS | zones and order correct |
| `run_wrong_order` | FAIL | `ORDER_VIOLATED` (B 1.8 s, A 4.8 s) |
| `run_missing_b` | FAIL | `OBJECT_NOT_FOUND` (B never appears while A does) |
| `run_hand_at_end` | REVIEW | `NOT_VISIBLE_AT_END` (hand covers A until the end) |

These are 5 **synthetic** cases (the same generator, flat blocks): they show that the flow works, not that it generalizes to real video. Measured latencies: reference analysis ≈18 s (Muse ≈11.6 s + SAM ≈4 s), verification ≈6–7 s. Absence verification is only declared for objects **never** detected in the clip; an object that disappears after being seen gives REVIEW, not FAIL (a single-call SAM cannot distinguish removal from occlusion).
