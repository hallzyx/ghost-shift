# GhostShift — Technical specification

Derived from `docs/PRD.md` (v1.0). The detailed design of the verifier engine is in `docs/engine/VERIFIER_ENGINE_SPEC.md`. Anything not verified against the real API is marked **[ASSUMPTION]** and must be checked during the API preflight (see `ROADMAP.md`).

## 1. Architecture decisions

| Decision | Choice | Reason |
|---|---|---|
| Backend | Python 3.11+ + FastAPI | Rule engine and geometry in plain Python (numpy/opencv); fast iteration |
| Frontend | React + Vite + TypeScript | A single 5-screen SPA; no SSR |
| Persistence | SQLite + a `data/` folder per session | No infrastructure; meets per-session isolation and explicit deletion |
| Long-running jobs | In-process queue (asyncio) + state in SQLite | Sufficient at this scale; no Redis |
| Verdict | In-house deterministic engine, no network | PRD §11: the LLM never decides PASS/FAIL |
| Models | Thin `MetaClient` with `model` configurable via env | PRD §11: no unmeasured parameters promised |

Guiding principle: **the models observe, the engine decides**. Muse Spark proposes; SAM 3.1 locates; the human approves; the deterministic engine judges.

## 2. Repository structure

```
ghost-shift/
├─ docs/                    PRD, this spec, roadmap, engine/
├─ backend/
│  ├─ app/
│  │  ├─ api/               FastAPI routes (procedures, runs, evidence)
│  │  ├─ meta/              MetaClient: muse.py, sam.py, preflight.py, audit log
│  │  ├─ pipeline/          analyze_reference.py, verify_run.py (orchestration)
│  │  ├─ engine/            events.py, rules.py, verdict.py, identity.py (no network)
│  │  ├─ schemas/           pydantic: Procedure, Rule, Track, Event, Verdict
│  │  ├─ storage/           SQLite + files, TTL and deletion
│  │  └─ video/             validation, frame extraction, evidence
│  └─ tests/                engine/ (synthetic tracks), contract/, e2e/
├─ frontend/                Screens A–E (PRD §10)
└─ eval/                    12-run dataset + metrics script
```

`engine/` imports nothing from `meta/` or the network: it is tested with synthetic tracks.

## 3. Pipeline

### 3.1 Teach (reference → rules)

1. **Preflight** (`video/validate`): MP4/WebM, duration and size within limits **[ASSUMPTION: read from `dev.meta.ai/docs`]**, orientation, fps; actionable rejection (EP-01).
2. **Muse Spark** receives the video and returns strict JSON: `objects[]` (id, short description, visual appearance), `zones[]` (name, approximate relative region), `events[]` (`place:X` in zone Z, approximate instant, confidence), `uncertainties[]`. Output is validated with pydantic; retry with the validation error as feedback (max 2).
3. **SAM 3.1** segments and tracks each proposed object (prompt = description) → a `Track` per object: bbox/centroid/area per frame (mask only for evidence frames), score, gaps.
4. **Engine** runs the event detector over the tracks and **cross-checks** it against the events proposed by Muse. A proposed event that SAM does not support is marked `hypothesis` and never becomes a rule by default (EP-02).
5. **Rule Studio**: the user enables/disables rules, edits order, confirms names and zones → `Procedure vN` is saved with `approved_by_user=true` (EP-03). Any later edit creates `vN+1`.

### 3.2 Verify (run → verdict)

1. Clip preflight + camera compatibility check against the reference (see engine §camera).
2. Muse Spark (optional, bounded): semantic matching of objects across clips when the approved descriptions are not enough.
3. SAM 3.1 with the approved descriptions → the run's `Track`s.
4. Engine: events → rule-by-rule evaluation → overall verdict (EP-05: FAIL > REVIEW > PASS).
5. Evidence generation (cropped frames with mask/box, instants) and an audit entry.

## 4. Data model (SQLite)

- `sessions(id, created_at, expires_at, consent_at)`
- `procedures(id, session_id, name, version, status[draft|approved], rules_json, objects_json, reference_video, created_at)`
- `runs(id, procedure_id, procedure_version, video_path, status, verdict, created_at)`
- `rule_results(run_id, rule_id, verdict, reason, evidence_json)`
- `model_calls(id, session_id, kind[muse|sam], model_version, request_id, latency_ms, status, error, created_at)` — audit (PRD §P0, §12); no personal content.

Constraint: `runs.procedure_version` can only reference `approved` procedures (EP-03).

## 5. REST API (backend)

| Method | Route | Function |
|---|---|---|
| POST | `/sessions` | Creates a session with explicit consent |
| POST | `/procedures` | Uploads the reference, starts analysis → `procedure_id` (draft) |
| GET | `/procedures/{id}` | Status by stage: interpretation / segmentation / proposal |
| PUT | `/procedures/{id}/rules` | Saves edits; `POST .../approve` creates the approved version |
| POST | `/procedures/{id}/runs` | Uploads a run; 409 if there is no approved version |
| GET | `/runs/{id}` | Verdict, rules, evidence |
| GET | `/runs/{id}/evidence/{n}` | Frame/mask |
| DELETE | `/sessions/{id}` | Explicit deletion of files and rows |
| GET | `/audit/{session_id}` | Log of calls and versions |

Model/network errors: response with `retryable: true` and the session is kept (EP-07). Empty segmentation → `NO_OBSERVATION` status, never PASS/FAIL.

## 6. Frontend

Screens A–E of PRD §10. Key components: `VideoPlayer` with synchronized timestamps; `RuleCard` (text, proposed/hypothesis state, toggle, order editing); `Timeline` (events + rule not met, click jumps to the instant); `EvidenceFrame` (highlighted mask); `VerdictBadge` with text + icon, not just color. Empty/error/retry states on every screen.

## 7. Security and privacy

- Meta keys only in the backend (`.env`, never in the bundle); `.env.example` without values.
- Consent before the first upload (notice that content is sent to an inference provider).
- Configurable session TTL (24 h by default) + explicit `DELETE`; logs without personal data.
- No public routes by default; session IDs are not enumerable (UUIDv4).
- Permanent notice: not suitable for critical controls.

## 8. Observability

Every model call is recorded in `model_calls`. Structured logs (JSON) with `request_id`, stage and duration. An `/audit` view supports the honesty check (PRD §15): it makes it possible to show that inference is live and that there is no per-procedure logic.

## 9. Testing

- **Engine unit tests** (no network): synthetic tracks → events/verdicts; properties: empty segmentation ⇒ never PASS; more uncertainty never turns REVIEW into PASS.
- **Contract**: validation of Muse/SAM outputs with recorded responses (for tests only, never in production runs).
- **E2E**: full flow with the `eval/` dataset and a metrics report (4/4 PASS, ≥5/6 FAIL, 2/2 REVIEW).
- **Anti-hardcode**: a test that fails if the repo contains IDs/colors/sequences of the evaluation procedures inside `engine/` or `pipeline/`.

## 10. Open assumptions (verify during preflight)

1. Muse Spark video input: URL, base64, sampled frames? Size/duration/fps limits.
2. SAM 3.1: does it accept text prompts for video, does it return per-frame masks or only per-clip? Format (RLE/PNG), object IDs, latency and cost.
3. Does Muse Spark reliably support structured JSON output/tool use? If not, validation + retry.
4. Quotas and rate limits for 12 runs + iteration.

If (2) does not deliver usable temporal tracking, the engine falls back to **states mode** (presence/position) — see the conditional go/no-go in PRD §13.
