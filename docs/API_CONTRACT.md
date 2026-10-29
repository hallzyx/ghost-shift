# GhostShift — API contract (frontend ⇄ backend)

FastAPI backend at `http://localhost:8000`. The frontend (Vite, `http://localhost:5173`) uses the `/api/*` proxy → backend (strips the `/api` prefix). Everything is JSON except uploads (`multipart/form-data`), video and frames. User-facing texts (fields ending in `_es`) are in **Spanish**. Errors: `{"detail": "message"}` with 4xx/5xx; model/network errors add `retryable: true`.

## Session (consent)
- `POST /sessions` `{consent:true}` → `201 {session_id, expires_at}` (400 if there is no consent). The frontend stores `session_id` in `localStorage`.
- `DELETE /sessions/{sid}` → `204` deletes files and data.
- `GET /sessions/{sid}/procedures` → `[{procedure_id, name, status, version, created_at, n_rules}]`. `status`: `analyzing | ready | failed | approved`.
- `GET /audit/{sid}` → `[{id, kind:"muse"|"sam", model_version, request_id, latency_ms, status, error, created_at}]`. `status:"cached"` = a recorded response was reused (same request over the same video bytes; cache in `data/model_cache`, can be disabled with `GHOSTSHIFT_MODEL_CACHE=""`).
- `GET /samples` → `[{id, kind:"reference"|"run", title_es, description_es, video_url, expected:"PASS"|"FAIL"|"REVIEW"|null}]` bundled sample videos (they allow trying the product without recording).

## Teach (reference → rules)
- `POST /sessions/{sid}/procedures/from-video` multipart `name`, `video` → `202 {procedure_id}`.
- `POST /sessions/{sid}/procedures/from-sample` JSON `{name, sample_id}` → `202 {procedure_id}`.
- `GET /procedures/{pid}` → **procedure view** (poll every ~1.5 s while `analysis.status == "running"`):
```json
{
  "procedure_id": "uuid", "name": "Kit A-B", "status": "analyzing|ready|failed|approved",
  "version": 1, "video_url": "/procedures/{pid}/video", "duration_ms": 8000, "width": 640, "height": 360,
  "analysis": {
    "status": "running|done|failed",
    "stages": [ {"id":"validate|interpret|segment|propose", "label":"…", "state":"pending|running|done|failed", "detail":"…"|null} ],
    "error": {"message":"…","retryable":true} | null
  },
  "draft": null | {
    "version": 1, "approved": false,
    "objects": [{"id":"A","description":"Cuadrado azul","sam_prompt":"blue square","confirmed_by_user":true}],
    "zones": [{"id":"z1","role":"workspace|target|staging","label":"Zona izquierda","polygon":[[x,y],…]}],
    "rules": [{"id":"R1","type":"present_in_zone|in_zone_at|before|stacked_on","enabled":true,"origin":"proposed|user|hypothesis",
               "text_es":"…","object":"A","zone":"z1","at":"end|during","first":"place:A","second":"place:B","base":"B"}],
    "timeline": [{"kind":"place|remove","object":"A","zone":"z1","t_ms":1800,"confidence":"sam_confirmed|muse_only"}],
    "uncertainties": ["text in Spanish", …]
  }
}
```
`description` = the name shown to the user (Spanish); `sam_prompt` = the short **English** phrase SAM uses to find the object (SAM does not understand Spanish; verified). The UI shows the description and lets the user edit `sam_prompt` in an advanced «Cómo lo busca la IA» (How the AI looks for it) section.
`stacked_on`: `object` must end up **directly on top of** `base` at the end of the clip (no `zone`); a tower of N pieces is N−1 rules. It is proposed when the reference ends with stacked objects; in that case no `before` is proposed between pieces of the same tower (stacking already implies the order). With a handheld camera, the zones are in coordinates of the reference's final frame (this is flagged in `uncertainties`).
Polygon coordinates are normalized 0–1 (origin top-left). `origin:"hypothesis"` = the AI suggests it but SAM does not support it: it must be shown as such and arrive **disabled**.
- `POST /procedures/{pid}/retry` → `202` retries a failed analysis.
- `PUT /procedures/{pid}/rules` `{draft:{objects,zones,rules}}` → `{procedure_id, version, status:"draft"}` (saves edits; 422 with an actionable `detail` if the procedure is invalid, e.g. an order cycle).
- `POST /procedures/{pid}/approve` → `{procedure_id, version, status:"approved", content_hash}` (422 if invalid). After editing an approved version a new version is created and must be re-approved.
- `GET /procedures/{pid}/video` MP4 stream (supports Range).

## Verify (run → verdict)
- `POST /procedures/{pid}/runs/from-video` multipart `video` → `202 {run_id}` (409 if there is no approved version).
- `POST /procedures/{pid}/runs/from-sample` `{sample_id}` → `202 {run_id}`.
- `GET /runs/{rid}` (poll while `status=="running"`):
```json
{
  "run_id":"uuid","procedure_id":"uuid","procedure_version":1,
  "status":"running|done|failed", "stages":[{"id":"validate|segment|verify","label":"…","state":"…","detail":null}],
  "error":{"message":"…","retryable":true}|null,
  "video_url":"/runs/{rid}/video","duration_ms":8000,
  "report": null | {
    "verdict":"PASS|FAIL|REVIEW", "camera_status":"ALIGNED|RECALIBRATED|UNCHECKED|INCOMPATIBLE",
    "camera":{"status":"RECALIBRATED","message_es":"…","aligned_to_reference":true,"max_shift":0.14,
              "registered_ratio":1.0,"reference_shift":0.0,"warning":true},
    "blocking_issues":["INSUFFICIENT_OBSERVATION|CAMERA_UNSTABLE|CAMERA_INCOMPATIBLE"],
    "rules":[{"rule_id":"R1","text_es":"…","verdict":"PASS|FAIL|REVIEW|SKIPPED","reason":"IN_ZONE","reason_es":"explanation in Spanish",
              "evidence":[{"kind":"event|state|absence_probe","obj":"A","t_ms":1800,"frame":18,"detail":"…","frame_url":"/runs/{rid}/frames/1800.jpg?obj=A"}],
              "missing":["…"]}],
    "events":[{"kind":"place","obj":"A","zone":"z1","t_lo":1000,"t_hi":1800,"timing_uncertain":false}]
  }
}
```
`camera` (camera notice; computed by the backend's OpenCV registration, the engine decides with it): `RECALIBRATED` = the camera moved and was compensated (zones follow the table); `INCOMPATIBLE` = moved too much (< 80 % of frames alignable) → global REVIEW `CAMERA_UNSTABLE`; `aligned_to_reference:false` = it could not be aligned with the reference → zone rules REVIEW `CAMERA_MOVED` (order/stacking rules are still evaluated); `UNCHECKED` = textureless background, not measurable. `max_shift`/`reference_shift` as a fraction of the diagonal. Show the notice when `warning` is `true`.
Reason codes added for stacking and identity: `STACKED`, `NOT_STACKED`, `STACK_INVERTED`, `STACK_NOT_VISIBLE_AT_END`, `STACK_UNCLEAR`, `IDENTITY_CONFLICT`, `CAMERA_UNSTABLE`.
- `POST /runs/{rid}/retry` → `202`.
- `GET /runs/{rid}/video` MP4 stream. `GET /runs/{rid}/frames/{t_ms}.jpg?obj=A` frame with the object's box highlighted.
- `GET /procedures/{pid}/runs` → `[{run_id, status, verdict, created_at}]`.

## Product rules the UI must respect
1. The models **propose**, the user **approves**, the engine **decides**: nothing becomes mandatory without approval; verification is not possible without an approved version.
2. **REVIEW ≠ FAIL**: REVIEW means insufficient observation (explain it, offer to retry with a better video).
3. Every FAIL/REVIEW shows the rule, object, instant and evidence frame; clicking the evidence jumps the video to `t_ms`.
4. The verdict does not rely on color alone: text + icon.
5. Permanent notice: not suitable for critical controls. Consent before the first upload.
6. Errors with retry; empty and loading states on every screen.
