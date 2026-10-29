# GhostShift

**Teach a task once. Verify the next run.** Upload a reference video; Muse Spark and SAM 3.1 (Meta API) propose objects, zones and rules; you approve them; a deterministic engine (no AI) compares new runs and returns PASS / FAIL / REVIEW with evidence. The models observe, the engine decides.

> Not intended for safety-critical, compliance or other critical controls.

## Requirements
Python 3.11+, Node 20+, `ffmpeg`/`ffprobe` on the PATH, and a Meta API key.

## Getting started
```bash
# 1) API key (backend only; never committed to git)
cp .env.example .env          # edit .env and set MODEL_API_KEY=<your key>   (META_API_KEY also works)

# 2) Backend  (http://localhost:8000)
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -e engine -e "backend[sam-masks]"
uvicorn app.main:app --app-dir backend --port 8000

# 3) Frontend (http://localhost:5173)
cd frontend && npm install && npm run dev
```
Open http://localhost:5173. In the Teach step (labelled «Enseñar» in the UI, which is currently in Spanish) you can use the bundled **synthetic sample videos** (a reference plus 4 runs: correct, reversed order, missing object, hand covering) or upload your own: table in view with some surface texture, camera as still as possible (handheld is tolerated), 2–4 objects in distinct colors, MP4/MOV, landscape recommended (portrait is accepted but untested), 2–120 s.

## Tests
```bash
(cd engine && python -m pytest) && (cd backend && python -m pytest)   # no network; they use recorded responses
```

## Layout
`engine/` deterministic engine (no network) · `backend/` FastAPI API, Muse/SAM clients, jobs · `frontend/` React SPA · `docs/` PRD, specs, API contract and measured findings about the Meta API (`docs/meta-findings.md`).

## Known limitations
Tested with synthetic videos and with **a single real video** (handheld phone, 3 stacked tape rolls; derived clips made with ffmpeg: trimmed, reversed, shakier, blurred, flipped). Details and numbers in `docs/meta-findings.md`.
- **Camera**: motion is compensated using the table texture (OpenCV, homography). If fewer than 80 % of frames can be aligned, the result is REVIEW («camera too shaky»); if the run cannot be aligned with the reference, zone rules go to REVIEW. On a **plain** table there is no texture: motion cannot be measured and a warning is shown («not checked»).
- **Stacking** (`stacked_on`): decided from 2D boxes at the end of the clip; with a single oblique camera, «behind» can look like «on top of». A tower needs one rule per piece.
- **Hands**: SAM returns a very large hand + arm box; any object under it counts as occluded, so if the hand is still on the table at the end the result is REVIEW, not FAIL.
- **Similar objects**: SAM may mark several pieces with the same concept («green tape roll» marked all three rolls). If they cannot be told apart, the result is REVIEW `IDENTITY_CONFLICT`.
- **Temporal order** (`before`) is unreliable with real hands (placement times come out with seconds of margin); it is not proposed for towers.
- Identity across clips is resolved by the object description (there is no visual correspondence). Model responses are stored in `data/model_cache` so the same video is never paid for twice.
