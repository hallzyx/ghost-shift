# GhostShift — Especificación técnica del MVP

Deriva de `docs/PRD.md` (v1.0). El diseño detallado del motor verificador está en `docs/engine/VERIFIER_ENGINE_SPEC.md`. Lo que no esté verificado contra la API real se marca **[SUPUESTO]** y se comprueba el 28–29 oct (ver `BACKLOG.md`, tarea T0).

## 1. Decisiones de arquitectura

| Decisión | Elección | Motivo |
|---|---|---|
| Backend | Python 3.12 + FastAPI | Motor de reglas y geometría en Python puro (numpy/opencv); iteración rápida |
| Frontend | React + Vite + TypeScript | Una sola SPA de 5 pantallas; sin SSR |
| Persistencia | SQLite + carpeta `data/` por sesión | Sin infraestructura; cumple aislamiento por sesión y borrado explícito |
| Trabajos largos | Cola en proceso (asyncio) + estado en SQLite | Suficiente para demo; sin Redis |
| Veredicto | Motor determinista propio, sin red | PRD §11: el LLM nunca decide PASS/FAIL |
| Modelos | Cliente fino `MetaClient` con `model` configurable por env | PRD §11: parámetros no prometidos |

Principio rector: **los modelos observan, el motor decide**. Muse Spark propone; SAM 3.1 localiza; el humano aprueba; el motor determinista juzga.

## 2. Estructura del repositorio

```
ghost-shift/
├─ docs/                    PRD, esta spec, backlog, engine/
├─ backend/
│  ├─ app/
│  │  ├─ api/               rutas FastAPI (procedures, runs, evidence)
│  │  ├─ meta/              MetaClient: muse.py, sam.py, preflight.py, audit log
│  │  ├─ pipeline/          analyze_reference.py, verify_run.py (orquestación)
│  │  ├─ engine/            events.py, rules.py, verdict.py, identity.py (sin red)
│  │  ├─ schemas/           pydantic: Procedure, Rule, Track, Event, Verdict
│  │  ├─ storage/           SQLite + archivos, TTL y borrado
│  │  └─ video/             validación, extracción de fotogramas, evidencia
│  └─ tests/                engine/ (pistas sintéticas), contract/, e2e/
├─ frontend/                Pantallas A–E (PRD §10)
└─ eval/                    dataset de 12 ejecuciones + script de métricas
```

`engine/` no importa nada de `meta/` ni de red: se prueba con pistas sintéticas.

## 3. Pipeline

### 3.1 Enseñar (referencia → reglas)

1. **Preflight** (`video/validate`): MP4/WebM, duración y tamaño dentro de límites **[SUPUESTO: se leen de `dev.meta.ai/docs`]**, orientación, fps; rechazo accionable (EP-01).
2. **Muse Spark** recibe el video y devuelve JSON estricto: `objects[]` (id, descripción corta, aspecto visual), `zones[]` (nombre, región relativa aproximada), `events[]` (`place:X` en zona Z, instante aproximado, confianza), `uncertainties[]`. Salida validada con pydantic; reintento con el error de validación como retroalimentación (máx. 2).
3. **SAM 3.1** segmenta y sigue cada objeto propuesto (prompt = descripción) → `Track` por objeto: bbox/centroide/área por fotograma (máscara solo para fotogramas de evidencia), score, huecos.
4. **Motor** ejecuta el detector de eventos sobre las pistas y **contrasta** con los eventos propuestos por Muse. Un evento propuesto que SAM no respalda se marca `hypothesis`, nunca se convierte en regla por defecto (EP-02).
5. **Rule Studio**: el usuario activa/desactiva reglas, edita orden, confirma nombres y zonas → se guarda `Procedure vN` con `approved_by_user=true` (EP-03). Cualquier edición posterior crea `vN+1`.

### 3.2 Verificar (ejecución → veredicto)

1. Preflight del clip + comprobación de compatibilidad de cámara contra la referencia (ver engine §cámara).
2. Muse Spark (opcional, acotado): correspondencia semántica de objetos entre clips cuando las descripciones aprobadas no bastan.
3. SAM 3.1 con las descripciones aprobadas → `Track`s de la ejecución.
4. Motor: eventos → evaluación regla a regla → veredicto global (EP-05: FAIL > REVIEW > PASS).
5. Generación de evidencia (fotogramas recortados con máscara/caja, instantes) y entrada de auditoría.

## 4. Modelo de datos (SQLite)

- `sessions(id, created_at, expires_at, consent_at)`
- `procedures(id, session_id, name, version, status[draft|approved], rules_json, objects_json, reference_video, created_at)`
- `runs(id, procedure_id, procedure_version, video_path, status, verdict, created_at)`
- `rule_results(run_id, rule_id, verdict, reason, evidence_json)`
- `model_calls(id, session_id, kind[muse|sam], model_version, request_id, latency_ms, status, error, created_at)` — auditoría (PRD §P0, §12); sin contenido personal.

Restricción: `runs.procedure_version` solo puede referenciar procedimientos `approved` (EP-03).

## 5. API REST (backend)

| Método | Ruta | Función |
|---|---|---|
| POST | `/sessions` | Crea sesión con consentimiento explícito |
| POST | `/procedures` | Sube referencia, inicia análisis → `procedure_id` (draft) |
| GET | `/procedures/{id}` | Estado por etapas: interpretación / segmentación / propuesta |
| PUT | `/procedures/{id}/rules` | Guarda ediciones; `POST .../approve` crea versión aprobada |
| POST | `/procedures/{id}/runs` | Sube ejecución; 409 si no hay versión aprobada |
| GET | `/runs/{id}` | Veredicto, reglas, evidencia |
| GET | `/runs/{id}/evidence/{n}` | Fotograma/máscara |
| DELETE | `/sessions/{id}` | Borrado explícito de archivos y filas |
| GET | `/audit/{session_id}` | Registro de llamadas y versiones |

Errores de modelo/red: respuesta con `retryable: true` y conservación de la sesión (EP-07). Segmentación vacía → estado `NO_OBSERVATION`, jamás PASS/FAIL.

## 6. Frontend

Pantallas A–E del PRD §10. Componentes clave: `VideoPlayer` con marcas temporales sincronizadas; `RuleCard` (texto, estado propuesto/hipótesis, toggle, edición de orden); `Timeline` (eventos + regla incumplida, clic salta al instante); `EvidenceFrame` (máscara resaltada); `VerdictBadge` con texto + icono, no solo color. Estados vacío/error/reintento en cada pantalla.

## 7. Seguridad y privacidad

- Claves Meta solo en backend (`.env`, nunca en bundle); `.env.example` sin valores.
- Consentimiento previo a la primera subida (aviso de envío a proveedor de inferencia).
- TTL de sesión configurable (por defecto 24 h) + `DELETE` explícito; logs sin datos personales.
- Sin rutas públicas por defecto; IDs de sesión no enumerables (UUIDv4).
- Aviso permanente: prototipo no apto para controles críticos.

## 8. Observabilidad

Cada llamada a modelo se registra en `model_calls`. Logs estructurados (JSON) con `request_id`, etapa, duración. Una vista `/audit` alimenta la prueba de honestidad de la demo (PRD §15): permite demostrar que la inferencia es en vivo y que no hay lógica por procedimiento.

## 9. Pruebas

- **Unitarias del motor** (sin red): pistas sintéticas → eventos/veredictos; propiedades: segmentación vacía ⇒ nunca PASS; más incertidumbre nunca convierte REVIEW en PASS.
- **Contrato**: validación de salidas de Muse/SAM con respuestas grabadas (solo para tests, nunca en la demo).
- **E2E**: flujo completo con el dataset `eval/` y reporte de métricas (4/4 PASS, ≥5/6 FAIL, 2/2 REVIEW).
- **Anti-hardcode**: test que falla si el repo contiene IDs/colores/secuencias de los procedimientos de demo dentro de `engine/` o `pipeline/`.

## 10. Supuestos abiertos (verificar el 28–29 oct)

1. Entrada de video de Muse Spark: ¿URL, base64, fotogramas muestreados? Límites de tamaño/duración/fps.
2. SAM 3.1: ¿acepta prompts de texto para video, devuelve máscaras por fotograma o solo por clip? Formato (RLE/PNG), IDs de objeto, latencia y costo.
3. ¿Muse Spark soporta salida JSON estructurada/tool use de forma fiable? Si no, validación + reintento.
4. Cuotas y rate limits para 12 ejecuciones + iteración.

Si (2) no entrega seguimiento temporal utilizable, el motor cae a **modo estados** (presencia/posición) — ver go/no-go condicional PRD §13.
