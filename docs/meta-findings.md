# Hallazgos de la API de Meta (T0)

Verificado con llamadas reales el **28 oct 2026** sobre un video **sintético** (2 bloques, 640×360, 10 fps, 8 s; generador y verdad de terreno en `backend/tests/fixtures/sam/`). Leyenda: ✅ comprobado con llamada real · ❌ falla / no se cumple · 📄 solo documentación · ⏳ sin probar. **Límite de la evidencia:** un único clip sintético con bloques planos; no hay manos reales, iluminación variable ni cámara móvil.

## Acceso
- `GET /v1/models` con `Authorization: Bearer <clave>` → 200. Modelos listados: `sam-3.1`, `muse-spark-1.3`, `muse-spark-1.3-contributor`, `muse-spark-1.2(-contributor)`, `muse-spark-1.1`, `muse-wonder-1.0`, `muse-image-1.0`, `muse-voice-transcribe-1.0`. ✅
- Variable de entorno: el entorno expone `META_API_KEY`; la doc oficial usa `MODEL_API_KEY`. El cliente acepta ambas. ✅
- **No usar** `muse-spark-1.3-contributor` (Meta puede entrenar con el contenido; incompatible con PRD §12). No se llamó. ✅

## SAM 3.1 (`POST /v1/responses`, streaming)
Cuerpo: `input=[{type:message, role:user, content:[{input_text: "<concepto>"},{input_video: video_url}]}]`, `stream:true`, `metadata:{include_confidence:"true"}` (cadena). El texto llega en eventos `response.output_text.delta`, uno por fotograma; termina en `response.completed` (con `usage.video_frames_processed`) y un `[DONE]`.

| # | Estado | Evidencia real |
|---|---|---|
| S1 | ✅ | "blue square" → solo A (56 fotogramas, 1 id); "yellow square" → solo B (38). El color filtra bien. Una petición por concepto. |
| S2 | ✅ (limitado) | Un único id (0) por petición durante todo el clip, incluso tras la oclusión (A reaparece con el mismo id). Con un clip simple no se pudo forzar un cambio de id; el adaptador sigue tratando cada id como tracklet aparte. |
| S3 | ✅ / ❌ | Con `include_confidence` llega `c` en caja y máscara. **Pero `c` fue constante por objeto** (A=0.9024 en los 56 fotogramas, B=0.9064), no por fotograma como dice la doc. **No cae bajo oclusión**, así que el motor no puede apoyarse en el score para detectar oclusión: debe usar ausencia/área/solape con `aux:hand` (spec §3.4). Sin la opción no hay `c`; el adaptador usa 0.9 por defecto. |
| S4 | ✅ | Formato exactamente el documentado. Caja en píxeles fuente con `w,h`. Máscara = **recorte de la caja** a resolución propia (`x=0;y=0` son desplazamientos dentro del recorte), relleno ≈1.0 en cuadrados. Alfabeto base85 propio (ASCII 33–123 sin `" , ; < > \ |`) y `~` es un codec de rango con contexto, no trivial: se usa el parser oficial `meta-sam-parser` 0.0.6 (SAM License) como dependencia opcional para máscaras. |
| S5 | ✅ | Índices `<Nf>` base 0 y coinciden con los fotogramas del archivo (A empieza en 11 = primer fotograma con 27 px visibles según la verdad de terreno). Fotogramas sin objeto no emiten línea. `video_frames_processed`=80 = fotogramas reales del archivo. |
| S6 | ✅ (parcial) | Data URL base64 acepta 7,7 KB (80 fotogramas) y 37 KB (**1280×720, 240 fotogramas, 24 s**: 12,9 s total). Latencia para el clip de 8 s: TTFB 0,9–2,0 s, **total 3,9–5,1 s**. Límite doc 📄: MP4/MOV (H.264/H.265/MPEG-4), hasta 15 000 fotogramas, 16 objetos por fotograma. Sin probar clips largos/pesados ni el límite de tamaño de la data URL ni `file_id` con SAM. |
| S7 | ✅ (con matices) | Con el bloque A **totalmente tapado** (fotogramas 60–70) SAM devolvió **ausencia** (sin línea), no máscaras alucinadas. Con oclusión parcial (58–59, 71–72) devuelve la caja del trozo visible. Defectos: 2 fotogramas con objeto visible sin detección (57, 73) → el motor debe tolerar huecos cortos. **"hand" devolvió 0 resultados** sobre mi "mano" (rectángulo color piel); **`aux:hand` queda ⏳ hasta probar con manos reales.** |
| S8 | ✅ (aprox.) | Dos llamadas idénticas: **cajas idénticas** en 56/56 fotogramas, pero **las máscaras difieren en bytes** en todas las líneas. Con vs. sin `include_confidence`: 1 de 56 cajas difiere 1 px. Reproducible a nivel de caja, no bit a bit ⇒ mantener caché por sha256 del video + prompt y no exigir igualdad bit a bit. No se devuelve versión de modelo más fina que `model: sam-3.1`. |
| S9 | ✅ | Todas las instancias del concepto por petición (aquí 1 por clip; no se probó con varias). |
| Precisión | ✅ | IoU medio con la verdad de terreno: A 0,969 (mín 0,918), B 0,967 (mín 0,959); 0 falsos positivos. |
| Coste | ✅ | `usage.video_frames_processed` = 80 por petición (mín. facturable 50); 📄 $0,20 / 1000 fotogramas. |
| `one_bit` | ✅ | `metadata.mask_encoding:"one_bit"` funciona y reduce el texto de 37 KB a 8 KB (mismas cajas). Recomendado si se guardan máscaras. |

### Consecuencias de diseño
1. Una petición SAM por objeto + una `aux:hand`, en paralelo (5 llamadas para 4 objetos). Las 3 del e2e tardaron ~4 s cada una.
2. **No usar `c` para decidir oclusión**; sí ausencia, caída de área y solape con la mano. Ajustar la spec §3.1 si el score constante se confirma en video real.
3. Cero deltas = resultado válido (ausencia), no error (tests con `hand_conf`).
4. `frame_t_ms` se calcula con el fps real (ffprobe) y `n_frames` real; SAM procesa todos los fotogramas del archivo. ✅ **Re-muestreo probado**: un video 1280×720 a 30 fps se normaliza en el backend a 960×540 a 10 fps; SAM y el motor dan los mismos instantes (A 1,8 s, B 4,8 s) que con el original a 10 fps.
5. ❌ **SAM no entiende prompts en español** ("cuadrado azul", "bloque azul", "mano" → 0 resultados). Cada objeto guarda un nombre en español para el usuario y un `sam_prompt` corto en inglés (lo propone Muse y el usuario puede editarlo).

## Muse Spark 1.3 (modo Standard) — `text.format` json_schema, strict
Se probó con el mismo video, subido por Files API (`POST /v1/files`, `purpose=user_data`, 200, `file-…`) y por `input_video` (data URL). Ambas rutas funcionan. Esquema: objetos / zonas (bbox normalizada) / eventos (`enter|place|remove|occlusion`, `t_seconds`).

| Aspecto | Estado | Resultado |
|---|---|---|
| JSON válido según esquema | ✅ | 2/2 respuestas válidas (con `strict:true`). |
| Objetos | ✅ / ❌ | Run 1 (file): A azul, B amarillo y un **objeto "C" inventado** (la mano, "peach square"). Run 2 (video): solo A y B. |
| Zonas | ✅ | Z1≈[0,24–0,33 × 0,41–0,59] y Z2≈[0,75–0,84 × 0,43–0,58] en run 2 (real: A 0,25–0,34 × 0,42–0,58; B 0,75–0,84 × 0,42–0,58). Run 1 más holgada pero correcta. |
| Instantes `enter/place` | ✅ (±0,5 s) | enter A 1,0 s (real 1,0); place A 2,1 (real ≈1,8); enter B 4,2 (real 4,0); place B 5,2 (real ≈4,8). Idéntico en ambas ejecuciones. |
| Oclusión | ❌ | Dijo 5,2 s y 6,3/7,3 s; real 5,7–7,3 s (mano). Evidencia textual inconsistente ("muted purple"). |
| Reproducibilidad | ❌ | Dos ejecuciones dieron resultados distintos (objeto C, número de eventos). |
| Latencia / coste | ✅ | 15–28 s por clip de 8 s; ~2,2 k tokens de entrada y 3–5 k de salida (casi todo razonamiento). |

**Conclusión:** útil para *proponer* objetos, zonas y orden aproximado (Fase de referencia, T3/T7), con la estructura garantizada por el esquema; **no es fiable para decidir tiempos exactos ni oclusión ni como fuente de veredicto**. Las propuestas deben ir como `proposed|hypothesis` y ser validadas por el usuario/SAM, como ya prevé el diseño. Lo medido sirve solo para este clip sintético.

## Verificación extremo a extremo (llamadas reales)
`backend/app/meta/sam_client.py` → 3 peticiones reales (`obj:A`, `obj:B`, `aux:hand`) → `sam_adapter.build_trackset` → `verify_run`: **PASS** (R1 IN_ZONE, R2 IN_ZONE, R3 ORDER_OK). El mismo resultado se reproduce offline en `backend/tests/test_sam_adapter.py` con respuestas crudas grabadas, y con las zonas intercambiadas el motor da **FAIL**.

## Pendiente / no verificado
- Manos reales (`aux:hand`), oclusión real, varias instancias del mismo concepto, cambio de ids tras salir/entrar de plano.
- Límite máximo de tamaño de data URL / `file_id` con SAM; clips de 30–60 s; límites de tasa (📄 ver `pricing-rate-limits`).
- Video móvil/VFR.
- Muse sobre grabaciones reales (la fiabilidad medida es solo la de un video sintético plano).

## Flujo completo de la app con llamadas reales (28 oct 2026)
Backend en marcha + video de referencia de ejemplo → Muse propone 2 objetos (en español, con `sam_prompt` en inglés) → SAM (3 peticiones en paralelo) → reglas propuestas (zonas desde la posición final de cada objeto; instantes 1,8 s y 4,8 s = verdad de terreno) → aprobación → 4 ejecuciones de ejemplo, todas con el veredicto esperado:

| Ejemplo | Veredicto | Motivo |
|---|---|---|
| `run_ok` | PASS | zonas y orden correctos |
| `run_wrong_order` | FAIL | `ORDER_VIOLATED` (B 1,8 s, A 4,8 s) |
| `run_missing_b` | FAIL | `OBJECT_NOT_FOUND` (B nunca aparece mientras A sí) |
| `run_hand_at_end` | REVIEW | `NOT_VISIBLE_AT_END` (mano tapa A hasta el final) |

Son 5 casos **sintéticos** (el mismo generador, bloques planos): demuestran que el flujo funciona, no que generalice a video real. Latencias medidas: análisis de referencia ≈18 s (Muse ≈11,6 s + SAM ≈4 s), verificación ≈6–7 s. La verificación de ausencia solo se declara para objetos **nunca** detectados en el clip; un objeto que desaparece tras verse da REVIEW, no FAIL (un SAM de una sola llamada no distingue retirada de oclusión).
