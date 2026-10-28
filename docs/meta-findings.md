# Hallazgos de la API de Meta (T0)

Fuente: documentación oficial en `dev.meta.ai/docs` leída el 28 oct 2026. **Nada de esto está verificado con llamadas reales todavía**: el host `api.meta.ai` estaba bloqueado por la política de red del entorno al escribir esto. Las filas marcadas ✅ salen de la documentación; ⏳ requieren una prueba real.

## Acceso
- Base URL `https://api.meta.ai/v1`, autenticación `Authorization: Bearer $MODEL_API_KEY` (variable de entorno oficial). ✅
- Ambos modelos usan `POST /v1/responses` (formato compatible con OpenAI Responses). ✅
- Nombres de modelo correctos: **`sam-3.1`** (no `sam-3-1`) y **`muse-spark-1.3`**. ✅
- **No usar** `muse-spark-1.3-contributor`: ese modo permite a Meta entrenar con el contenido enviado, incompatible con el consentimiento del PRD §12. Usar siempre modo Standard. ✅

## SAM 3.1 (resuelve los supuestos S1–S9 de `engine/VERIFIER_ENGINE_SPEC.md`)
| # | Estado | Hallazgo |
|---|---|---|
| S1 | ✅ | Prompt por concepto: un sustantivo corto por petición ("blue square"). No admite listas ni comandos; para varios objetos hay que hacer **una petición por concepto** (o prompts de caja/punto con ids propios). Admite atributos (color) para filtrar. |
| S2 | ✅ | Devuelve caja + máscara por objeto y fotograma, con **id estable por respuesta** mientras el objeto esté en plano; no fiable tras salir/entrar o con oclusión total ⇒ el adaptador debe tratar un id nuevo como posible tracklet distinto (spec §1.2). |
| S3 | ✅ | La confianza solo llega con `include_confidence: "true"` (campo `c`, 0–1, por registro). Sin esa opción no hay score. |
| S4 | ✅ | Salida en texto con tokens especiales: `<Nf>id<\|box;x1..y2;w;h\|><\|mask;x=0;y=0;data=H,W,ENCpayload\|>`. Cajas en píxeles de origen; máscara base85 (`~` sin pérdida, `!` 1 bit) a resolución propia menor que el fotograma. Existe parser oficial `@meta-sam/parser` (TS); en Python hay que escribir el parser. |
| S5 | ✅ | El índice `<Nf>` es del fotograma fuente, base 0, puede saltar y **un fotograma sin objetos no emite línea**. Hay que derivar `frame_t_ms` del fps real del archivo (ffprobe). No existe rango "procesado": el adaptador lo define como todo el clip. |
| S6 | ⏳ | Entrada de video: MP4/MOV (H.264, H.265, MPEG-4) por `input_video` con URL pública, data URL base64 o `file_id` (Files API). Límites de tamaño/duración y latencia sin medir. |
| S7 | ⏳ | Comportamiento ante oclusión por manos sin medir (ausencia vs máscara espuria). |
| S8 | ⏳ | Reproducibilidad entre llamadas idénticas sin medir. Mantener caché por sha256. |
| S9 | ✅ | Un concepto devuelve **todas** las instancias; ids por instancia. |
| — | ✅ | Precio: $0,20 por 1.000 fotogramas de video (mínimo 50 por petición). Un clip de 30 s a 10 fps ≈ 300 fotogramas ≈ $0,06 por objeto. Límites de tasa por equipo (ver `pricing-rate-limits`). |

### Consecuencias para el diseño
1. **Una petición SAM por objeto** (más una para `aux:hand`): con 4 objetos, 5 llamadas por clip. Paralelizar.
2. **Re-muestreo a ~10 fps en cliente** (ffmpeg) antes de enviar: abarata y fija `analysis_fps`. ⏳ confirmar que SAM acepta el video re-codificado y que los índices coinciden.
3. **Sondeo de ausencia (spec §4.4):** una petición cuyo resultado vacío es válido ("cero coincidencias" = stream sin deltas), por lo que el `AbsenceProbe` se puede implementar con una llamada extra sobre los últimos fotogramas; el score exige `include_confidence`.
4. El adaptador debe **tratar 0 deltas como resultado válido**, no como error.

## Muse Spark 1.3
- Entrada de video por `input_file` (`file_id` tras subir con Files API, `purpose: "user_data"`) o `input_video` (URL/base64). Lee también audio. ✅
- Salida estructurada documentada en `/docs/structured-output` (no revisada aún). ⏳ validar JSON estricto con el esquema de objetos/zonas/eventos.
- Ventana de contexto 1.048.576 tokens; $1,25/M entrada, $4,25/M salida (Standard). ✅

## Pendiente (requiere acceso a `api.meta.ai`)
- Smoke test real: `sam-3.1` sobre un video sintético de dos bloques y comparar contra la verdad de terreno.
- Medir latencia, límites de tamaño, comportamiento en oclusión y reproducibilidad (S6–S8).
- Probar salida estructurada de Muse Spark con video.
