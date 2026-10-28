# GhostShift — Backlog ejecutable

Fechas según PRD §14 (entrega: 4 nov, 9:00 p. m. Lima). Prioridad P0/P1 del PRD. Estimaciones en horas de una persona. Cada tarea tiene un criterio de terminado verificable.

## Compuertas go/no-go

| Compuerta | Fecha | Condición para continuar |
|---|---|---|
| G1 | 29 oct | Muse y SAM responden sobre un clip real; se obtienen pistas por objeto con huecos tolerables |
| G2 | 30 oct | Detector detecta ≥1 evento `place:X` estable en el clip de referencia sin valores fijos por video |
| G3 | 31 oct | Orden funciona; si no → **conditional go** (solo estados), reencuadrar el pitch |

## 28 oct — Viabilidad
- **T0 (P0, 3h)** Preflight de APIs: límites de video, formato de entrada, salida de SAM, JSON de Muse, cuotas. Documentar en `docs/meta-findings.md`. *Hecho cuando* los 4 supuestos de TECH_SPEC §10 están confirmados o refutados.
- **T1 (P0, 2h)** Grabar 2 procedimientos × (1 referencia + ejecuciones). Cámara fija, 3 objetos de colores distintos. Guía de grabación en `docs/recording-guide.md`.
- **T2 (P0, 2h)** Esqueleto del repo, `MetaClient`, `.env.example`, auditoría `model_calls`.

## 29 oct — Observación
- **T3 (P0, 4h)** `analyze_reference`: Muse → JSON validado (objetos/zonas/eventos/incertidumbres), con reintento.
- **T4 (P0, 4h)** SAM → `Track` por objeto; normalización de salida; manejo de huecos.
- **T5 (P0, 2h)** Validación de video (EP-01) y fotogramas de evidencia.
- **G1** al cierre del día.

## 30 oct — Reglas
- **T6 (P0, 6h, ⚠ crítica)** Detector de eventos + esquema de reglas, según `engine/VERIFIER_ENGINE_SPEC.md`. Con tests sintéticos.
- **T7 (P0, 3h)** Generación de reglas candidatas (Muse + respaldo SAM) con estado `proposed|hypothesis`.
- **T8 (P0, 3h)** Versionado de procedimientos y aprobación (EP-03), restricción de borrador.
- **G2** al cierre del día.

## 31 oct — Verificador
- **T9 (P0, 6h, ⚠ crítica)** Evaluador de reglas (presencia, posición, orden) y veredicto 3-valuado (EP-05).
- **T10 (P0, 3h)** Correspondencia de identidad entre clips + disparo de confirmación humana.
- **T11 (P0, 2h)** Evidencia: fotograma/máscara/instante por regla.
- **G3** al cierre del día.

## 1 nov — Generalización
- **T12 (P0, 3h)** Segundo procedimiento desde cero **sin tocar código** (se decide al final; registrar en el log).
- **T13 (P0, 2h)** Test anti-hardcode y revisión de que `engine/` y `pipeline/` no contienen lógica por procedimiento.
- **T14 (P0, 3h)** Casos límite PRD §9 (oclusión, solo final, cámara movida, objetos casi idénticos).

## 2 nov — Producto
- **T15 (P0, 8h)** Frontend A–E: subida, análisis por etapas, Rule Studio, verificación, resultado con línea de tiempo.
- **T16 (P0, 2h)** Errores/reintento (EP-07), consentimiento, borrado de sesión.
- **T17 (P1, 3h)** Comparador lado a lado / export JSON — solo si T15 está cerrada.

## 3 nov — Validación y entrega
- **T18 (P0, 4h)** Dataset de 12 ejecuciones + `eval/run_eval.py`; registrar resultados **reales**, incluidos los fallos.
- **T19 (P0, 3h)** README, arquitectura, variables de entorno, límites, evidencia de contribuciones durante la hackathon.
- **T20 (P0, 3h)** Grabar demo de 3 min según guion PRD §15 (sin presentar inferencia grabada como en vivo).

## 4 nov — Cierre
- **T21 (P0)** Congelar versión, repositorio público, enlaces accesibles, formulario y miembros del equipo antes de las 9:00 p. m. (Lima). Margen recomendado: enviar a las 5:00 p. m.

## Tareas críticas (para quien las asuma)

| Tarea | Por qué es crítica | Mitigación |
|---|---|---|
| T6/T9 motor | Riesgo "Crítica" PRD §17; define si el producto es honesto | Spec dedicada, tests sintéticos, G2/G3 |
| T0 preflight | Todo depende de lo que la API realmente permita | Primer bloque del día 1 |
| T12 segundo procedimiento | Prueba anti-hardcode ante jurado | Elegirlo tarde, ejecutarlo sin cambios de código |

## Riesgos de calendario
- 7 días con una persona: si T6 se atrasa >1 día, activar **conditional go** y recortar T10/T17.
- Frontend (T15, 8h) es la mayor tarea P0 no crítica: construir contra un backend con respuestas reales desde el 31 oct.
