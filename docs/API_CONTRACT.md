# GhostShift — Contrato de API (frontend ⇄ backend)

Backend FastAPI en `http://localhost:8000`. El frontend (Vite, `http://localhost:5173`) usa el proxy `/api/*` → backend (quita el prefijo `/api`). Todo es JSON salvo subidas (`multipart/form-data`), vídeo y fotogramas. Los textos para el usuario van en **español**. Errores: `{"detail": "mensaje"}` con 4xx/5xx; los de modelos/red añaden `retryable: true`.

## Sesión (consentimiento)
- `POST /sessions` `{consent:true}` → `201 {session_id, expires_at}` (400 si no hay consentimiento). El frontend guarda `session_id` en `localStorage`.
- `DELETE /sessions/{sid}` → `204` borra archivos y datos.
- `GET /sessions/{sid}/procedures` → `[{procedure_id, name, status, version, created_at, n_rules}]`. `status`: `analyzing | ready | failed | approved`.
- `GET /audit/{sid}` → `[{id, kind:"muse"|"sam", model_version, request_id, latency_ms, status, error, created_at}]`.
- `GET /samples` → `[{id, kind:"reference"|"run", title_es, description_es, video_url, expected:"PASS"|"FAIL"|"REVIEW"|null}]` vídeos de ejemplo incluidos (permiten probar sin grabar).

## Enseñar (referencia → reglas)
- `POST /sessions/{sid}/procedures/from-video` multipart `name`, `video` → `202 {procedure_id}`.
- `POST /sessions/{sid}/procedures/from-sample` JSON `{name, sample_id}` → `202 {procedure_id}`.
- `GET /procedures/{pid}` → **vista del procedimiento** (hacer polling cada ~1.5 s mientras `analysis.status == "running"`):
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
    "rules": [{"id":"R1","type":"present_in_zone|in_zone_at|before","enabled":true,"origin":"proposed|user|hypothesis",
               "text_es":"…","object":"A","zone":"z1","at":"end|during","first":"place:A","second":"place:B"}],
    "timeline": [{"kind":"place|remove","object":"A","zone":"z1","t_ms":1800,"confidence":"sam_confirmed|muse_only"}],
    "uncertainties": ["texto en español", …]
  }
}
```
`description` = nombre en español para el usuario; `sam_prompt` = frase corta **en inglés** con que SAM busca el objeto (SAM no entiende español; verificado). El UI muestra la descripción y deja editar `sam_prompt` en un apartado «Cómo lo busca la IA» (avanzado).
Coordenadas de polígonos normalizadas 0–1 (origen arriba-izquierda). `origin:"hypothesis"` = la IA lo sugiere pero SAM no lo respalda: debe mostrarse como tal y venir **desactivada**.
- `POST /procedures/{pid}/retry` → `202` reintenta un análisis fallido.
- `PUT /procedures/{pid}/rules` `{draft:{objects,zones,rules}}` → `{procedure_id, version, status:"draft"}` (guardar ediciones; 422 `detail` con error accionable si el procedimiento es inválido, p. ej. ciclo de orden).
- `POST /procedures/{pid}/approve` → `{procedure_id, version, status:"approved", content_hash}` (422 si inválido). Tras editar una versión aprobada se crea una versión nueva y hay que re-aprobar.
- `GET /procedures/{pid}/video` stream MP4 (admite Range).

## Verificar (ejecución → veredicto)
- `POST /procedures/{pid}/runs/from-video` multipart `video` → `202 {run_id}` (409 si no hay versión aprobada).
- `POST /procedures/{pid}/runs/from-sample` `{sample_id}` → `202 {run_id}`.
- `GET /runs/{rid}` (polling mientras `status=="running"`):
```json
{
  "run_id":"uuid","procedure_id":"uuid","procedure_version":1,
  "status":"running|done|failed", "stages":[{"id":"validate|segment|verify","label":"…","state":"…","detail":null}],
  "error":{"message":"…","retryable":true}|null,
  "video_url":"/runs/{rid}/video","duration_ms":8000,
  "report": null | {
    "verdict":"PASS|FAIL|REVIEW", "camera_status":"ALIGNED", "blocking_issues":["INSUFFICIENT_OBSERVATION"],
    "rules":[{"rule_id":"R1","text_es":"…","verdict":"PASS|FAIL|REVIEW|SKIPPED","reason":"IN_ZONE","reason_es":"explicación en español",
              "evidence":[{"kind":"event|state|absence_probe","obj":"A","t_ms":1800,"frame":18,"detail":"…","frame_url":"/runs/{rid}/frames/1800.jpg?obj=A"}],
              "missing":["…"]}],
    "events":[{"kind":"place","obj":"A","zone":"z1","t_lo":1000,"t_hi":1800,"timing_uncertain":false}]
  }
}
```
- `POST /runs/{rid}/retry` → `202`.
- `GET /runs/{rid}/video` stream MP4. `GET /runs/{rid}/frames/{t_ms}.jpg?obj=A` fotograma con la caja del objeto resaltada.
- `GET /procedures/{pid}/runs` → `[{run_id, status, verdict, created_at}]`.

## Reglas de producto que el UI debe respetar
1. Los modelos **proponen**, el usuario **aprueba**, el motor **decide**: nada se vuelve obligatorio sin aprobación; no se puede verificar sin versión aprobada.
2. **REVIEW ≠ FAIL**: REVIEW significa observación insuficiente (explicarlo, ofrecer reintentar con mejor video).
3. Todo FAIL/REVIEW muestra regla, objeto, instante y fotograma de evidencia; clic en la evidencia salta el vídeo a `t_ms`.
4. El veredicto no usa solo color: texto + icono.
5. Aviso permanente: prototipo, no apto para controles críticos. Consentimiento antes de la primera subida.
6. Errores con reintento; estados vacíos y de carga en cada pantalla.
