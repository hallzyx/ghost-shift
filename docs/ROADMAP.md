# GhostShift — Roadmap

Workstreams in dependency order, with priorities (P0/P1) from the PRD. Each item has a verifiable acceptance criterion. Estimates are in hours for one person.

## Go/no-go gates

| Gate | Condition to continue |
|---|---|
| G1 | Muse and SAM respond on a real clip; per-object tracks are obtained with tolerable gaps |
| G2 | The detector finds ≥1 stable `place:X` event in the reference clip without per-video fixed values |
| G3 | Order works; if not → **conditional go** (states only), reframe the product claim |

## 1. Viability
- **API preflight (P0, 3h)** Video limits, input format, SAM output, Muse JSON, quotas. Document in `docs/meta-findings.md`. *Done when* the four open assumptions in TECH_SPEC §10 are confirmed or refuted.
- **Recording set (P0, 2h)** Record 2 procedures × (1 reference + runs). Fixed camera, 3 objects in distinct colors. Recording guide in `docs/recording-guide.md`.
- **Repository skeleton (P0, 2h)** `MetaClient`, `.env.example`, `model_calls` audit.

## 2. Observation
- **`analyze_reference` (P0, 4h)** Muse → validated JSON (objects/zones/events/uncertainties), with retry.
- **SAM tracks (P0, 4h)** SAM → `Track` per object; output normalization; gap handling.
- **Video validation (P0, 2h)** Validation (EP-01) and evidence frames.
- **G1** after this workstream.

## 3. Rules
- **Event detector and rule schema (P0, 6h, critical)** Per `engine/VERIFIER_ENGINE_SPEC.md`, with synthetic tests.
- **Candidate rule generation (P0, 3h)** Muse + SAM fallback, with `proposed|hypothesis` status.
- **Procedure versioning and approval (P0, 3h)** EP-03, draft restriction.
- **G2** after this workstream.

## 4. Verifier
- **Rule evaluator (P0, 6h, critical)** Presence, position and order, with a three-valued verdict (EP-05).
- **Identity matching across clips (P0, 3h)** Plus triggering human confirmation.
- **Evidence (P0, 2h)** Frame/mask/instant per rule.
- **G3** after this workstream.

## 5. Generalization
- **Second procedure (P0, 3h)** From scratch **without touching code** (chosen last; recorded in the log).
- **Anti-hardcode test (P0, 2h)** Review that `engine/` and `pipeline/` contain no per-procedure logic.
- **Edge cases (P0, 3h)** PRD §9 (occlusion, end-only, moved camera, nearly identical objects).

## 6. Product
- **Frontend A–E (P0, 8h)** Upload, staged analysis, Rule Studio, verification, result with timeline.
- **Errors and privacy (P0, 2h)** Errors/retry (EP-07), consent, session deletion.
- **Comparison / export (P1, 3h)** Side-by-side comparison / JSON export — only once the frontend is complete.

## 7. Validation and release
- **Evaluation set (P0, 4h)** 12 runs + `eval/run_eval.py`; record **real** results, including failures.
- **Documentation (P0, 3h)** README, architecture, environment variables, limits.
- **Release (P0)** Freeze the version and verify links and access before publishing.

## Critical items

| Item | Why it is critical | Mitigation |
|---|---|---|
| Engine (detector + evaluator) | "Critical" risk in PRD §17; determines whether the product is honest | Dedicated spec, synthetic tests, G2/G3 |
| API preflight | Everything depends on what the API actually allows | First block of work |
| Second procedure | Anti-hardcode proof | Choose it late, run it without code changes |

## Schedule risks
- If the engine work slips significantly, activate **conditional go** and trim identity matching and the P1 items.
- The frontend is the largest non-critical P0 item: build it against a backend with real responses as early as possible.
