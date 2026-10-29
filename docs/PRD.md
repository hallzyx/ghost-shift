# GhostShift — Product Requirements Document (PRD)

**Version:** 1.0 — October 28, 2026  
**Status:** Proposal for validation; capabilities not yet demonstrated

## 1. Executive summary

**GhostShift turns a video demonstration into a reusable visual verifier for physical procedures.** A person records how a structured task is done; the system identifies observable objects and events, proposes rules (presence, placement and order), asks for a short confirmation, and then analyzes a new run. The result is **PASS**, **FAIL** or **REVIEW**, together with visual evidence and explanations.

**Product promise:** «Teach a task once. Verify the next run.»

**Hypothesis to validate:** it is possible to obtain verifiable rules for a *new* physical procedure without training specialized models and without writing logic specific to that procedure. A demonstration alone does not establish what is normatively required, which is why the user must approve the proposed rules.

GhostShift does **not** aim to certify industrial processes, assess human safety, or understand arbitrary tasks. Its initial scope is a tabletop setting, a fixed camera, a few clearly distinguishable objects and observable visual transitions.

## 2. Problem and opportunity

For short, repetitive manual tasks (e.g., preparing kits or assembling simple components), turning a demonstration into digital checks can require configuration, labeling or specialized engineering. This makes it hard to introduce visual quality controls in small or changing processes.

**Specific problem:** a supervisor knows the correct order but lacks a quick way to turn it into observable checks and to explain exactly where a new run deviated from what was expected.

**Existing alternatives:** industrial visual inspection platforms, checklists, written procedures and tools that generate instructions from videos. GhostShift does not claim to have invented visual inspection; its aspirational differentiation is **fast configuration from a single example, with transparent rules and auditable evidence**.

## 3. Users and use cases

**Primary user:** the person responsible for preparing or reviewing a repetitive light-assembly, packaging or kit-preparation process in a controlled setting.

**Secondary user:** the operator or reviewer who performs the procedure and needs to know which condition was not met.

**Main case:** assembling a kit of three components A, B and C on a surface, placing them in their zones and following a defined order.

**Similar supported cases, used to check generalization:** another kit with different objects and a different sequence; a simple sorting task with 2–4 visible items.

## 4. Goals, metrics and limits

### 4.1 Product goals

1. Turn a reference video into **understandable, editable rules**, not just a narrative summary.
2. Reuse those rules on an independent run without changing code.
3. Report the result with visual evidence, observed events and a concrete cause.
4. Acknowledge uncertainty and request review when objects are not sufficiently observable.
5. Make the use of Muse Spark and SAM 3.1 transparent through an audit log of every model call.

### 4.2 Prototype acceptance metrics (targets, not results)

- **Minimum generalization:** two different procedures created from different reference videos; the second requires no code changes and no preloaded procedure-specific rules.
- **Accuracy on a controlled evaluation set:** four of four correct runs accepted; at least five of six deliberately incorrect runs rejected; two visually ambiguous clips sent to **REVIEW**.
- **Traceability:** every FAIL identifies the rule, object, instant/frame and associated evidence; an error is never shown without an observable condition.
- **User-configurable:** the essential steps are confirmed from the interface without frame-by-frame manual labeling.
- **Real operation:** evaluation uses the genuine model calls and the same verifier as the product; results presented as inference are not precomputed.
- **Target usability:** from uploading a valid video to confirming rules, a first-time user can complete the guided flow without editing files or code.

These figures are *go/no-go* criteria for the prototype stage, **not** sufficient metrics for an industrial deployment.

## 5. MVP scope

### Included (P0: essential)

- Upload of a **reference video** and a **run video**.
- Supported MP4/WebM formats, with file, duration and orientation validation before processing.
- A fixed-camera setup with a full view of a table or delimited surface.
- **2–4 visually distinguishable objects**, with short names or descriptions the user can confirm.
- Analysis with Muse Spark to propose observable objects, steps and logical order.
- Segmentation/tracking with SAM 3.1 to obtain spatial and temporal evidence.
- Rules for **object presence**, **entry/position in a zone** and **precedence A before B**.
- A review screen where the user accepts, disables or edits proposed rules (including order), with simple validation.
- Compilation of approved rules into a structured, executable representation.
- Verification of another run and **PASS / FAIL / REVIEW** results per rule and overall.
- Timeline with evidence frames, highlighted masks or boxes and an understandable explanation.
- Log of calls, model versions, approved rules and results so every verdict can be audited.
- A second, different procedure to show that no sequence is hand-coded.

### Desirable (P1: only if P0 works)

- Capture from the browser camera, in addition to uploading clips.
- Side-by-side comparison of the reference video and the run.
- Export a JSON or PDF report with rules and evidence.
- A visual editor for zones of interest to correct an automatically proposed zone.
- Simple per-step timing metrics.

### Out of scope (P2 / future)

- Live video with low-latency alerts.
- Multiple cameras, moving cameras or 3D reconstruction.
- Precise hand tracking, force estimation or checking of invisible actions.
- Integration with PLCs, robots, MES/ERP systems or industrial cameras.
- Safety certification, risk control for people, employee monitoring or individual productivity assessment.
- Model training/fine-tuning and universal recognition of arbitrarily similar objects.
- Fault detection in long, overlapping procedures or ones with many occluded objects.

## 6. Main user journey

**Step 1 — Create a procedure.** The person opens GhostShift, chooses «Teach a new procedure», reads the video requirements and uploads a reference recording.

**Step 2 — Analyze.** GhostShift identifies the relevant elements and proposes a timeline: which object enters which zone and in what order. The user sees the analysis status and the parts that could not be interpreted.

**Step 3 — Approve rules.** The person reviews an understandable list (e.g., «The blue component must be in zone A at the end» and «A must be placed before B»), corrects what is needed and clicks «Save procedure». No ambiguous inference silently becomes an obligation.

**Step 4 — Verify.** The person uploads a new run of the same procedure. GhostShift reuses the saved rules, observes objects and events again and computes the result.

**Step 5 — Understand the verdict.** An overall status and a list of rules are shown; those not met include temporal and visual evidence. If the observation is insufficient, REVIEW is shown, not an automatic FAIL.

**Step 6 — Test transfer.** The user teaches a different procedure with new objects and order; GhostShift generates new rules using the same architecture.

## 7. Functional requirements and acceptance criteria

### EP-01 — Create a procedure

**US-01.** As a supervisor, I want to upload a demonstration so that I can start a visual specification without writing code.

**Acceptance:** a compatible MP4/WebM can be uploaded; preview, duration and processing status appear; unreadable files show an actionable error; the user cannot start verification before saving rules.

### EP-02 — Propose visual rules

**US-02.** As a supervisor, I want the AI to identify objects, events and dependencies so that manual configuration is reduced.

**Acceptance:** the system proposes a structured list of objects/zones/events/rules; each rule has understandable text; if an action is not visible or cannot be inferred, it is marked as a hypothesis or uncertainty; proposals are not confused with confirmed facts.

### EP-03 — Confirm and edit

**US-03.** As a supervisor, I want to approve or correct the rules so that I decide what counts as correct.

**Acceptance:** I can enable/disable a rule, change the expected order and confirm object identifiers; changes are saved in a versioned procedure; no verification uses unapproved draft versions.

### EP-04 — Inspect a new run

**US-04.** As a reviewer, I want to upload another video and see compliance with specific rules.

**Acceptance:** the system uses the approved rules; computes observable events from the new clip; distinguishes «object present» from «correct order», so that two runs with the same final state can produce different results.

### EP-05 — Evidence and verdicts

**US-05.** As a reviewer, I want to understand why the system approved, rejected or could not decide.

**Acceptance:** each rule shows PASS, FAIL or REVIEW, together with temporal evidence; a FAIL contains the rule not met and an event that contradicts it; REVIEW explains the missing data; the overall status is FAIL if any failure is confirmed, REVIEW if there are no failures but at least one rule is uncertain, and PASS only if all rules are verified.

### EP-06 — Demonstrable generalization

**US-06.** As an evaluator, I want to teach a different task to check that the product is not coded for a single example.

**Acceptance:** the second procedure can be created from scratch, with its own objects and rules; verification uses a generic engine; no new code versions are deployed and no hidden settings are changed to accept it.

### EP-07 — Basic robustness

**US-07.** As a user, I want to know what failed and how to retry.

**Acceptance:** network/model errors show a visible message and a retry option; clips with a moving camera, objects out of frame or low visibility trigger a warning; an empty segmentation does not produce an artificial PASS or FAIL.

## 8. Product evaluation rules

- **Presence:** a confirmed object must exist and be identifiable in a relevant temporal state.
- **Position:** an object must occupy a defined zone; the zone is represented in scene-relative coordinates.
- **Order:** placement event A must occur before event B; if the system only sees final states, it cannot claim to have verified the sequence.
- **Minimum persistence:** to avoid false events, a placement may require stability for a configurable number of frames.
- **Uncertainty:** occlusion, doubtful identity, temporary absence of detection or significant camera shift lead to REVIEW when they prevent a condition from being checked.
- **Identity across videos:** the object IDs returned by SAM are not assumed to persist between clips; objects are matched by visual/semantic description and zone verification, and confirmation is requested if the match is ambiguous.

**Rule contract (illustrative):**

```json
{
  "procedure_id": "kit-001",
  "version": 1,
  "objects": [
    {"id":"A","description":"blue component"},
    {"id":"B","description":"yellow component"}
  ],
  "rules": [
    {"id":"R1","type":"present_in_zone","object":"A","zone":"left","at":"end"},
    {"id":"R2","type":"before","first":"place:A","second":"place:B"}
  ],
  "approved_by_user": true
}
```

## 9. States and edge cases

- **No file:** start screen with instructions, an example and recording constraints.
- **Video without detectable objects:** explanation plus a recommendation to record again; no verdict.
- **Hands cover an object:** REVIEW for the affected rules; do not automatically assume the object is missing.
- **Same components, wrong order:** precedence FAIL even if the final state is valid.
- **Correct order, object outside the zone:** position FAIL, not order.
- **Two nearly identical objects:** request human identification/correction; do not claim a confident match.
- **Only the end of the task is visible:** order rules must stay in REVIEW.
- **Strong camera or framing change:** show incompatibility or request recalibration.
- **Later rule edits:** create a new version and make clear that earlier results correspond to the version used.
- **API outage or timeout:** offer a retry and keep the session data if possible.

## 10. Experience and interface

**Screen A: Start.** «Teach procedure» CTA, a visual example, recording requirements.

**Screen B: Analysis.** Original video, progress by stage (interpretation, segmentation, rule proposal), issues.

**Screen C: Rule Studio.** Editable list of rules, thumbnails or timestamps, approve and save buttons; state explicitly that the AI proposes and the user defines the norm.

**Screen D: Verification.** Upload of the second video and selection of the versioned procedure.

**Screen E: Result.** PASS/FAIL/REVIEW header, rules table, timeline and highlighted frames; clicking evidence jumps to the instant in the clip.

**UX principles:** explanation before opaque scores; one primary action per screen; show uncertainty; visible labels, not just colors; accessible on a modern desktop.

## 11. Meta AI integration (functional limits)

**Muse Spark (preferred: `muse-spark-1.3`):** understand the reference video, propose objects and steps, produce candidate structured rules and help resolve semantic correspondences. Its proposals require validation by observation and human approval. It can act as a coordinator of calls and tool actions, without claiming unrestricted autonomy.

**SAM 3.1 (`sam-3.1`):** locate, segment and track objects within a clip. Masks and trajectories feed the verifier's event detector.

**In-house deterministic engine:** convert geometry and time into events; run presence/position/order rules; compute PASS/FAIL/REVIEW with evidence and record uncertainty. The final verdict is never delegated solely to a free-form LLM response.

**Operating condition:** check the current service limits for video size, duration, fps, costs, formats and latency before implementing. Keep model parameters configurable and do not promise unmeasured figures.

Official technical references:
- https://dev.meta.ai/docs/models
- https://dev.meta.ai/docs/sam/overview
- https://dev.meta.ai/docs/media-segmentation

## 12. Non-functional requirements, security and privacy

- **Credential security:** API keys only in the backend; never embedded in the frontend.
- **Consent:** do not upload recordings with identifiable people or private information without permission; state that they will be sent to an inference provider.
- **Retention:** delete temporary files after the session or allow explicit deletion; any persistent retention must be consented to and documented.
- **Isolation:** each procedure and its videos belong to a session; no automatic public exposure.
- **Observability:** keep request IDs, status, errors, model version and timings in technical logs, avoiding unnecessary personal data.
- **Stated limitation:** experimental product; not suitable for safety-critical controls, legal compliance or automated employment decisions.
- **Target compatibility:** modern desktop browser; mobile is not a P0 requirement.

## 13. Validation plan and go/no-go decision

**Minimum controlled dataset:**

- Two independent procedures, each with its reference and approved rules.
- Twelve run videos in total: four correct, six with distinct real errors and two with deliberately insufficient evidence.
- Changes of pace and gestures among the correct examples; at least one pair with an identical final state but a different order.

**Go:** generalization to two processes is demonstrated without hidden adjustments, 4/4 correct PASS, 5/6 FAIL detected, 2/2 ambiguous REVIEW and reasonably precise evidence.

**Conditional go:** if presence and position work but order does not, keep an honest MVP limited to states and reduce the ambition of the proposal; avoid describing it as a sequence verifier.

**No-go:** if verdicts require fixed values for each video, if unobserved events are invented, or if it cannot work on a new task. In that case, rethink the product before spending time on visual polish.

## 14. Validation milestones

| Milestone | Required result |
|---|---|
| 1. API viability | Access to Muse Spark/SAM validated and a reference clip processed |
| 2. Observation | Objects, masks and events obtained; initial go/no-go decision |
| 3. Rules | Rule generation and approval + JSON contract |
| 4. Verifier | Presence, position and order verifier + evidence |
| 5. Generalization | A second new task and generalization tests |
| 6. Interface | Complete interface and state/error handling |
| 7. Evaluation | 12-run evaluation, fixes and documentation |

Feasibility tests take priority. If the interpretation of temporal events fails at milestones 2–3, do not continue as if sequence verification were solved.

## 15. Reference acceptance scenario

A run-through that exercises the full product end to end; it is also a manual acceptance test.

1. **Problem:** show a manual task with no quick, verifiable control.
2. **Teach:** upload a new demonstration; show the real analysis with Muse Spark and SAM.
3. **Convert:** approve the rules the system proposes, not a hard-coded sequence.
4. **Verify:** upload a run with the wrong order, even if it ends with the pieces correctly placed.
5. **Evidence:** show the FAIL with the exact instant and the rule not met.
6. **Transfer:** a procedure with new objects and a different sequence; show the rules created without editing code.
7. **Wrap-up:** explain the usefulness, the limits and the «video to verifier» differentiator.

**Honesty of the walkthrough:** record the real experience; shorten waits transparently if stated, but never present recorded responses as live inference or hide per-procedure code changes.

## 16. Release checklist and definition of done

- [ ] Working application with the full teaching → confirmation → verification → evidence flow.
- [ ] At least two different procedures verified with the same code.
- [ ] Test suite and measured results documented; record real failures and limits.
- [ ] Repository with README, architecture, run instructions, environment variables and warnings.
- [ ] Explicit evidence of Meta model usage (call audit log).
- [ ] Walkthrough recording and an accessible deployment for review.

**«Done» criterion:** a person can teach a compatible process, accept rules, analyze another run and trace the evidence behind the verdict without a developer modifying the logic for that process.

## 17. Risks and open decisions

| Risk | Severity | Mitigation |
|---|---|---|
| Temporal events cannot be inferred reliably | Critical | Early tests; restrict actions to stable entries into zones |
| A single run does not define what is mandatory | High | Explicit rule approval and versioning |
| Objects confused between clips | High | Distinguishable objects, confirmed descriptions, REVIEW under uncertainty |
| Occlusion or poor camera | High | Recording guidance and REVIEW state |
| Competition from industrial solutions | High | Demonstrate configuration from an unknown procedure without specific training |
| APIs, latency and cost | Medium-high | Preflight of formats/limits and budgets; optimized video upload |
| Attractive but hard-coded results | Critical | Second procedure chosen last, logs and an auditable repository |

**Decisions left for the technical phase:** recommended minimum framing, exact duration and fps, zone-definition method, final event schema, geometric thresholds and frontend/backend stack. They will be chosen after testing with real data, not by assumption.

---

**PRD status:** ready to start technical validation. It is not evidence that the model already meets these criteria.
