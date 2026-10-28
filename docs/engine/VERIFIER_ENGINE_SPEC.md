# GhostShift — Especificación técnica del motor determinista de eventos y veredictos

**Versión del documento:** 0.1 (borrador de diseño) — 28 oct 2026
**Alcance:** motor que convierte pistas de SAM 3.1 + procedimiento aprobado en eventos, veredictos PASS/FAIL/REVIEW, evidencias y registro de auditoría. **Fuera de alcance:** frontend, orquestación y prompts de Muse Spark, llamadas HTTP a SAM (solo se define el contrato que el adaptador debe entregar).
**Referencias:** PRD v1.0, §7 (EP-04, EP-05, EP-07), §8, §9, §11, §13, §17.

Convenciones: **[DECISIÓN]** = elección cerrada para el MVP con su justificación; **[SUPUESTO]** = hecho no verificado sobre APIs externas, con comprobación asignada al día 1; `t` siempre en milisegundos desde el inicio del clip; coordenadas siempre normalizadas a `[0,1]`.

---

## 0. Principios de diseño

1. **El veredicto es una función pura** `verify_run(procedimiento, pistas, calibración, pistas_identidad, parámetros) → RunReport`. Mismas entradas ⇒ salida byte a byte idéntica (excepto el sobre de auditoría con marcas de reloj). Sin red, sin aleatoriedad, sin LLM en la ruta del veredicto (PRD §11).
2. **FAIL exige una observación contradictoria positiva** (un evento o estado visto con calidad suficiente). La falta de datos nunca produce FAIL; produce REVIEW (PRD §8, EP-07).
3. **Una laguna nunca borra un cambio de estado**: lo convierte en un evento con intervalo temporal ancho. Así la degradación de la observación solo puede mover veredictos hacia REVIEW (propiedad de monotonía, §7.4).
4. **Parámetros globales, nunca por vídeo ni por procedimiento** en el MVP. Evita el no-go del PRD §13 («valores fijos para cada video») y el riesgo crítico de hardcodeo (§17).
5. **Tiempo en ms, espacio en unidades normalizadas**, de modo que cambios de fps o de ritmo no alteren la semántica.

---

## 1. Contrato de entrada: pistas de SAM 3.1

### 1.1 Frontera de responsabilidad

[DECISIÓN] Un **adaptador** fuera del motor (`backend/adapters/sam_adapter.py`) traduce la respuesta cruda de SAM a un `TrackSet` canónico. El motor nunca ve el formato del proveedor. Justificación: el API de SAM 3.1 no está verificado; aislarlo permite que el motor y sus tests avancen el 28–29 oct con pistas sintéticas y que un cambio de formato solo afecte al adaptador y a sus *golden tests* con respuestas crudas grabadas.

### 1.2 Esquema `TrackSet` (pydantic v2, `schema_version = "ghostshift.tracks/1"`)

```python
class ClipMeta(BaseModel):
    clip_id: str                 # uuid de sesión
    sha256: str                  # hash del archivo de vídeo
    width: int; height: int      # píxeles del vídeo analizado
    analysis_fps: float          # fps efectivo de los fotogramas enviados/devueltos
    frame_t_ms: list[int]        # timestamp de cada fotograma analizado (monótono)
    duration_ms: int

class FrameObs(BaseModel):       # observación de un tracklet en un fotograma
    f: int                       # índice en frame_t_ms
    score: float                 # [0,1], confianza de la instancia en ese fotograma
    bbox: tuple[float,float,float,float]   # x0,y0,x1,y1 normalizados
    mask_rle: RLE | None         # COCO RLE (counts, size) a resolución de análisis
    # área, centroide y fracción en zona los calcula el motor (features.py)

class Tracklet(BaseModel):
    track_id: str                # SOLO válido dentro de este clip
    prompt_id: str               # objeto/concepto con que se pidió ("obj:A", "aux:hand")
    obs: list[FrameObs]          # fotogramas SIN observación = ausentes en la lista
    processed_frames: tuple[int,int]  # rango que SAM procesó (distingue "no visto" de "no procesado")

class AbsenceProbe(BaseModel):   # resultado de re-sondeo explícito (ver §4.4)
    prompt_id: str; frames: list[int]; max_score: float

class TrackSet(BaseModel):
    schema_version: Literal["ghostshift.tracks/1"]
    clip: ClipMeta
    model: ModelRef              # id ("sam-3.1"), versión devuelta, request_ids
    tracklets: list[Tracklet]
    absence_probes: list[AbsenceProbe] = []
    background_keyframes: list[str]  # rutas a 3 fotogramas (inicio/medio/fin) para calibración
```

Decisiones del contrato:

- **[DECISIÓN] Los huecos se representan por ausencia en `obs`**, no por máscaras vacías, y `processed_frames` acota lo que realmente se procesó. Un fotograma fuera de `processed_frames` es *no observado*; dentro y sin `FrameObs` es *no detectado*. Ambos son distintos de *visible fuera de zona*.
- **[DECISIÓN] Los IDs no persisten entre clips ni se asumen estables dentro del clip**: un objeto puede llegar fragmentado en varios tracklets (pérdida y readquisición). La agrupación tracklet→objeto la hace `identity.py` (§5).
- **[DECISIÓN] Se pide un concepto auxiliar `aux:hand`** en la misma llamada de SAM. Sus máscaras solo se usan para marcar oclusión (§3.4), nunca para eventos. Si el API no admite el concepto, el motor degrada a la heurística de caída de área (§3.4) y lo registra.
- **[DECISIÓN] `analysis_fps` objetivo = 10.** Una colocación humana dura 0,5–2 s; 10 fps da 5–20 fotogramas por colocación, suficiente para la ventana de estabilidad (600 ms = 6 fotogramas) con coste 3× menor que 30 fps. Si SAM impone su propio muestreo, el motor lo acepta: todo se expresa en ms.

### 1.3 Supuestos sobre el API de SAM 3.1 y comprobaciones del día 1

| # | [SUPUESTO] (no verificado en https://dev.meta.ai/docs/sam/overview) | Comprobación día 1 (clip de 10 s, 3 objetos + manos) | Si falla |
|---|---|---|---|
| S1 | Acepta **prompts de texto/concepto** en vídeo (no solo puntos/cajas) | Pedir "blue block", "hand"; ver si devuelve instancias | Prompt por caja del fotograma 0 tomada de la referencia vía Muse Spark; identidad depende más de la apariencia (§5) |
| S2 | Devuelve **máscara por instancia y por fotograma** con ID estable dentro del clip | Contar IDs distintos por objeto a lo largo del clip | Si solo devuelve por fotograma sin tracking: asociación por IoU fotograma a fotograma en el adaptador (greedy, IoU≥0,3) |
| S3 | Hay un **score por instancia y fotograma** en `[0,1]` | Histograma de scores con objeto visible vs tapado | Si el score es por pista: usar área relativa como proxy de calidad; recalibrar `score_visible` |
| S4 | Formato de máscara **RLE/PNG/polígono** decodificable localmente | Decodificar y superponer 5 fotogramas | Adaptador convierte a RLE; si solo hay bbox, `mask_rle=None` (el motor usa bbox, §3.1) |
| S5 | Correspondencia **índice de fotograma ↔ timestamp** recuperable; fps de muestreo controlable | Comparar nº de fotogramas devueltos con duración | Re-muestrear en cliente (ffmpeg) a 10 fps y enviar fotogramas o vídeo re-codificado |
| S6 | Límites de duración/tamaño/latencia compatibles con clips de 20–60 s | Medir latencia y tamaño máximo aceptado | Recortar/comprimir; límite de producto = el medido |
| S7 | Un objeto oculto produce **ausencia o score bajo**, no una máscara alucinada en otro sitio | Tapar un objeto 2 s con la mano | Subir `score_visible`; activar regla de salto espacial imposible (§3.5) |
| S8 | Versión de modelo identificable y salida reproducible | Dos llamadas idénticas; comparar | Cachear `TrackSet` por `sha256` del vídeo + prompts; el motor se re-ejecuta sobre caché |
| S9 | Un prompt puede devolver **varias instancias** | Dos objetos del mismo color | Resolución de duplicados en §5.2 |

Todas las respuestas crudas del día 1 se guardan en `engine/tests/fixtures/sam_raw/` y se convierten en tests del adaptador.

---

## 2. Esquema de procedimiento y reglas (`ghostshift.procedure/2`)

### 2.1 Esquema

```json
{
  "schema_version": "ghostshift.procedure/2",
  "procedure_id": "kit-001",
  "version": 3,
  "parent_version": 2,
  "approved_by_user": true,
  "approved_at": "2026-10-30T15:02:11-05:00",
  "content_hash": "sha256:…",
  "scene": {
    "reference_clip_sha256": "…",
    "frame_aspect": 1.7778,
    "background_fingerprint": {"keyframe": "ref_bg.png", "orb_keypoints": 412}
  },
  "objects": [
    {"id": "A", "description": "componente azul", "confirmed_by_user": true,
     "signature": {"hsv_hist": [/* 8x4x4 normalizado */], "area_norm": 0.012, "aspect": 1.4},
     "ref_keyframes": [{"f": 87, "mask_rle": {"…": "…"}}],
     "indistinguishable_from": []}
  ],
  "zones": [
    {"id": "workspace", "role": "workspace", "polygon": [[0.05,0.10],[0.95,0.10],[0.95,0.95],[0.05,0.95]]},
    {"id": "left", "label": "zona izquierda", "role": "target", "source": "auto",
     "polygon": [[0.12,0.40],[0.30,0.40],[0.30,0.62],[0.12,0.62]]}
  ],
  "rules": [
    {"id": "R1", "type": "in_zone_at", "object": "A", "zone": "left", "at": "end",
     "enabled": true, "origin": "proposed", "text_es": "El componente azul debe estar en la zona izquierda al finalizar"},
    {"id": "R2", "type": "in_zone_at", "object": "A", "zone": "left", "at": "during",
     "from": "place:A", "to": "end", "enabled": false, "origin": "proposed",
     "text_es": "Una vez colocado, el componente azul no debe salir de la zona izquierda"},
    {"id": "R3", "type": "before", "first": "place:A", "second": "place:B",
     "enabled": true, "origin": "user", "text_es": "A debe colocarse antes que B"},
    {"id": "R4", "type": "present_in_zone", "object": "C", "zone": "workspace",
     "enabled": true, "origin": "proposed", "text_es": "El componente C debe aparecer en la mesa"}
  ]
}
```

### 2.2 Semántica de tipos

| Tipo | Campos | Verdadero cuando… |
|---|---|---|
| `present_in_zone` | `object`, `zone` (por defecto `workspace`) | Existe un tramo de fotogramas VISIBLE ≥ `presence_min_ms` con el objeto dentro de la zona (presencia del PRD §8) |
| `in_zone_at` + `at:"end"` | `object`, `zone` | En la ventana final el objeto está VISIBLE y dentro de la zona (§4.3) |
| `in_zone_at` + `at:"during"` | `object`, `zone`, `from` (ref. evento), `to` (`"end"` o ref. evento) | El objeto permanece en la zona en todo el intervalo, sin evento `remove` observado |
| `before` | `first`, `second`: `place:<obj>` o `place:<obj>@<zona>`; `occurrence` (por defecto `"both_agree"`) | El evento `first` termina antes de que empiece `second` (intervalos, §4.5) |

- [DECISIÓN] `place:X` **sin zona** significa «X se movió y quedó en reposo» en cualquier punto del `workspace` (§3.2), no «X entró en su zona objetivo». Justificación: PRD §9 exige «orden correcto, objeto fuera de zona ⇒ FAIL de posición, no de orden»; si `place:B` dependiera de la zona correcta, colocar B mal causaría también FAIL de orden. La variante `place:X@Z` existe para procedimientos donde el orden solo importa dentro de una zona.
- [DECISIÓN] **Migración v1→v2:** el ejemplo del PRD `{"type":"present_in_zone", …, "at":"end"}` se migra automáticamente a `in_zone_at` con `at:"end"`; `present_in_zone` sin `at` mantiene su significado de presencia. La migración se registra en auditoría.
- **Roles de zona:** `workspace` (exactamente una; área válida de la mesa), `target` (zonas de reglas), `staging` (opcional, origen de piezas; solo informativa).

### 2.3 Validación al compilar (`compile_procedure`)

Rechazo (error accionable para Rule Studio): `approved_by_user=false`; referencias a objetos/zonas inexistentes; grafo de `before` con ciclos (orden topológico imposible); `first == second`; polígono no simple o área < 0,002; ninguna regla habilitada. Advertencia (no bloquea): dos zonas `target` con IoU > 0,3; objetos con `indistinguishable_from` no vacío (§5.3); regla `before` sobre objetos sin ninguna regla de posición (el `EVENT_NOT_OCCURRED` quedará en REVIEW, §4.5).

Cada edición produce `version+1` con `parent_version` y nuevo `content_hash`; los `RunReport` almacenan `(procedure_id, version, content_hash)` y nunca se re-etiquetan (PRD §9 «edición posterior»). `CompiledProcedure` es un `dataclass(frozen=True)` con polígonos ya rasterizados por resolución.

### 2.4 Definición de zonas

[DECISIÓN] Las zonas `target` se **derivan automáticamente de la referencia**: bbox de la máscara del objeto en su reposo final estable, ampliada `max(30 % de su tamaño, 0,03)` por lado y recortada al `workspace`; Muse Spark solo propone la etiqueta («zona izquierda»). El `workspace` es el casco convexo de todas las posiciones de reposo observadas en la referencia, ampliado 0,05. Justificación: es determinista, auditable y no requiere editor de zonas (P1). El usuario puede cambiar etiqueta o desactivar la regla; la edición geométrica queda para P1.

### 2.5 Normalización ante cambios de encuadre e incompatibilidad de cámara

Las zonas viven en coordenadas normalizadas **del fotograma de referencia**. Para cada ejecución, `calibration.py` estima `T_ref→exec` y transforma los **polígonos** (no las pistas):

1. Fondo: mediana de los 3 `background_keyframes`, reducida a 320 px de ancho en gris, con objetos y manos enmascarados (máscaras del propio `TrackSet`).
2. ORB (500 puntos) + `estimateAffinePartial2D` RANSAC (similitud de 4 GDL: traslación, rotación, escala uniforme) entre fondo de referencia y de ejecución.
3. Fallback si `inliers < 25` o `inlier_ratio < 0,4` (mesa sin textura): correlación de fase (solo traslación) + NCC del fondo alineado.

| Resultado | Condición | Efecto |
|---|---|---|
| `ALIGNED` | traslación ≤ 0,03·diag, rot ≤ 2°, escala ∈ [0,97, 1,03] | Aplica T silenciosamente |
| `RECALIBRATED` | traslación ≤ 0,10·diag, rot ≤ 5°, escala ∈ [0,90, 1,10] | Aplica T; aviso visible en el informe |
| `INCOMPATIBLE` | fuera de lo anterior, o relación de aspecto distinta (> 1 %) , o fallback con NCC < 0,6 | No se evalúan reglas; global REVIEW con `CAMERA_INCOMPATIBLE` y mensaje «recalibrar/regrabar» (PRD §9) |

**Movimiento intra-clip:** se estima T entre el fondo del primer y del último segundo. Si la traslación > 0,02·diag o rot > 1,5° ⇒ `CAMERA_MOVED`: todas las reglas dependientes de zonas pasan a REVIEW. Justificación: con cámara fija (requisito P0) es barato (2 estimaciones por clip, < 100 ms) y cualquier deriva mayor invalida las zonas más rápido de lo que podemos corregirlo con fiabilidad.

[DECISIÓN] `calibration.py` es el único módulo que depende de OpenCV (`opencv-python-headless`), y su resultado entra a `verify_run` como dato (`CalibrationResult`). El núcleo (eventos/reglas/veredicto) se testea sin imágenes.

---

## 3. Detector de eventos `place:X` y `remove:X`

### 3.1 Rasgos por fotograma (`features.py`)

Para cada objeto ya resuelto (§5) y cada fotograma analizado `f`:

- `area`, `centroid`, `bbox` (de la máscara; si `mask_rle=None`, del bbox).
- `inside[z] = |máscara ∩ zona z| / |máscara|` con la zona rasterizada a la resolución de la máscara. [DECISIÓN] Fracción de área en vez de «centroide dentro»: tolera objetos grandes junto al borde y da un valor continuo para histéresis.
- `hand_overlap = |bbox_objeto ∩ máscara_mano| / |bbox_objeto|`.
- **Estado de observación** (`obs_state`):
  - `VISIBLE`: score ≥ `score_visible` y `area ≥ frag_ratio · area_ref` y `hand_overlap < hand_occl`.
  - `OCCLUDED`: detectado pero con score bajo, área fragmentada o mano encima.
  - `ABSENT`: procesado y sin detección.
  - `UNOBSERVED`: fuera de `processed_frames`.
  `area_ref` = mediana del área en fotogramas con score ≥ 0,7 del propio clip (robusto a escala de cámara).

Solo los fotogramas `VISIBLE` cuentan como evidencia positiva o contradictoria. `OCCLUDED/ABSENT/UNOBSERVED` son **lagunas**.

### 3.2 Máquina de estados por objeto

Eventos genéricos de reposo, luego anotados con zona:

```
estados: UNKNOWN_INIT → RESTING(pos) ⇄ MOVING → CANDIDATE(pos) → RESTING(pos')
                         ↘ GAP (laguna) ↗

para cada fotograma VISIBLE:
  v = desplazamiento del centroide en la ventana de stable_ms
  si estado ∈ {RESTING} y |centroid − pos_reposo| > still_eps:   → MOVING (t_move_lo = último VISIBLE en reposo)
  si estado ∈ {MOVING, CANDIDATE}:
      si v ≤ still_eps durante ≥ stable_ms de fotogramas VISIBLE:
          si dist(pos_nueva, pos_reposo_anterior) ≥ move_min o el objeto entró desde fuera del workspace:
              emitir place(X, zona=argmax_z inside[z] si ≥ θ_in, si no None,
                           t_lo = t_move_lo, t_hi = t_inicio_ventana_estable)
          → RESTING(pos_nueva)       # si no hubo desplazamiento suficiente: ajuste, no evento
  histéresis de zona en RESTING: zona_actual cambia a None solo si inside < θ_out durante ≥ exit_ms VISIBLE
      → emitir remove(X, zona, t_lo, t_hi)
```

- **Estado inicial:** el primer tramo estable VISIBLE fija `RESTING(pos0)` **sin evento** y se marca `initial_rest = {pos0, zona}`. Un objeto que ya está en su zona desde el primer fotograma nunca genera `place` ⇒ base del caso «solo se ve el final» (§4.6).
- **Entrada desde fuera de plano:** si el primer tramo VISIBLE comienza tocando el borde del `workspace` y se estabiliza dentro, se emite `place` con `t_lo` = primer fotograma visible (el objeto fue *traído*).
- **Intervalo del evento:** `[t_lo, t_hi]` delimita con certeza el instante de la colocación: antes de `t_lo` estaba en otro sitio (visto), desde `t_hi` está quieto en el nuevo sitio (visto). El instante mostrado al usuario es `t_hi` (el primer fotograma de evidencia estable) y el fotograma clave es el de mayor score en la ventana estable.

### 3.3 Parámetros (globales, `EngineParams` congelado, con hash en auditoría)

| Parámetro | Defecto | Motivo |
|---|---|---|
| `analysis_fps` | 10 | §1.2 |
| `score_visible` | 0,50 | [SUPUESTO S3]; recalibrar con el histograma del día 1 |
| `frag_ratio` | 0,55 | Una mano que tapa ~la mitad deja el objeto como OCCLUDED |
| `hand_occl` | 0,15 | Solape mano/bbox por encima del cual la posición no es fiable |
| `θ_in` / `θ_out` | 0,60 / 0,35 | Histéresis: evita parpadeo en el borde de la zona |
| `stable_ms` | 600 | Persistencia mínima (PRD §8); > duración de pausas de agarre (~300 ms) |
| `still_eps` | 0,010 · diag | Ruido de centroide de SAM esperado < 0,5 % |
| `move_min` | 0,05 · diag | Distingue colocación real de reajuste |
| `exit_ms` | 300 | Salida de zona confirmada |
| `max_gap_ms` | 1000 | Puente de lagunas cortas (mano pasando) |
| `end_window_ms` | 1000 | Ventana del estado final |
| `end_visible_ratio` | 0,70 | Cobertura mínima en la ventana final |
| `presence_min_ms` | 500 | Presencia sostenida |
| `coverage_min` | 0,90 | Cobertura para afirmar «el evento no ocurrió» |

Todos los umbrales temporales se convierten a fotogramas con `ceil(ms · fps / 1000)`. [DECISIÓN] No hay overrides por procedimiento en el MVP (principio 4); un cambio de defaults es un cambio de versión del motor y obliga a re-evaluar las 12 ejecuciones (§7.5).

### 3.4 Oclusión por manos

1. Si hay máscara `aux:hand`: fotogramas con `hand_overlap ≥ hand_occl` ⇒ OCCLUDED.
2. Si no hay (S1 falla): OCCLUDED si `area < frag_ratio · area_ref` o score cae > 0,3 respecto a la mediana móvil de 1 s.
3. Durante OCCLUDED la máquina **no avanza ni reinicia**: no cuenta para la ventana de estabilidad ni para `exit_ms`. Consecuencia buscada: la colocación se fecha cuando la mano se retira y el objeto está quieto y visible, que es lo que realmente es observable.

### 3.5 Lagunas (detección ausente)

Al terminar una laguna `[g0, g1]` y volver a VISIBLE:

- Si `g1 − g0 ≤ max_gap_ms` **y** `dist(pos_antes, pos_después) ≤ still_eps·3` ⇒ puente: se continúa como si no hubiera laguna.
- Si la posición cambió ≥ `move_min` (o la laguna es larga y la posición cambió) ⇒ **evento con intervalo ancho**: `place` con `t_lo = g0` (último visible en el sitio anterior), `t_hi` = inicio de la nueva ventana estable, y `timing_uncertain = true`. No se descarta nunca (principio 3).
- Si la posición no cambió pero la laguna > `max_gap_ms` ⇒ se registra `gap` sin evento; las reglas `during` que cubran la laguna no pueden ser TRUE (§4.4).
- **Salto imposible:** si el objeto aparece a > 0,25·diag de su última posición en < 200 ms sin mano cerca, se trata como posible confusión de instancia: el tramo se marca `identity_suspect` y sus eventos llevan esa marca (⇒ REVIEW en reglas que los usen).

### 3.6 Reinicios y múltiples colocaciones

- Cada `place` lleva un ordinal por objeto (`k = 1, 2, …`). Un reajuste < `move_min` no es colocación.
- Se definen dos ocurrencias canónicas por objeto: **primera** (`k=1`) y **definitiva** (último `place` tras el cual el objeto no vuelve a moverse ≥ `move_min` hasta el final).
- [DECISIÓN] `before` usa por defecto `occurrence:"both_agree"`: se evalúa con ambas ocurrencias; si coinciden, ese es el resultado; si discrepan ⇒ REVIEW con `ORDER_AMBIGUOUS_REPLACEMENT` y ambos pares de evidencia. Justificación: «A, B, reajusto A» y «B, retiro B, A, B (corrección)» tienen lecturas normativas opuestas que un operador humano decide mejor; el dataset de errores deliberados del PRD §13 no incluye correcciones, así que el coste en recall de FAIL es nulo allí. `occurrence:"first"` y `"definitive"` quedan disponibles en el esquema para que el usuario lo fije en Rule Studio.

---

## 4. Lógica de veredicto

### 4.1 Semántica de tres valores

Cada evaluador devuelve `Outcome(value ∈ {TRUE, FALSE, UNKNOWN}, reason_code, evidence[], missing[])` con la correspondencia TRUE→PASS, FALSE→FAIL, UNKNOWN→REVIEW. Las combinaciones internas usan lógica de Kleene fuerte (`AND(FALSE, UNKNOWN)=FALSE`, `AND(TRUE, UNKNOWN)=UNKNOWN`).

**Compuertas previas** (se aplican antes del evaluador; cualquiera fuerza UNKNOWN para las reglas afectadas):

| Compuerta | Ámbito | Razón |
|---|---|---|
| `INSUFFICIENT_OBSERVATION` | global: ningún objeto con ≥ `presence_min_ms` VISIBLE | PRD §9 «sin objetos detectables»; EP-07 |
| `CAMERA_INCOMPATIBLE` / `CAMERA_MOVED` | global / reglas con zona | §2.5 |
| `IDENTITY_UNCONFIRMED` | reglas que mencionan un objeto ambiguo | §5 |
| `IDENTITY_SUSPECT` | reglas que usan un evento marcado | §3.5 |

### 4.2 Regla de oro de FAIL

[DECISIÓN] Un evaluador solo puede devolver FALSE si adjunta al menos una `Evidence` de tipo `event` o `state` construida con fotogramas VISIBLE (o un `AbsenceProbe` confirmado, §4.4). El agregador lo comprueba y degrada a UNKNOWN (`INTERNAL_NO_EVIDENCE`, registrado como bug) si no se cumple. Esto implementa EP-05 («un FAIL contiene… un evento que la contradice») como invariante, no como convención.

### 4.3 `in_zone_at` (`at: end`)

Ventana `W` = últimos `end_window_ms` analizados. `V` = fotogramas VISIBLE de `W`.

1. `|V|/|W| < end_visible_ratio`:
   - si el objeto salió observablemente del `workspace` (últimos VISIBLE tocando borde con velocidad hacia fuera) ⇒ FALSE `OBJECT_REMOVED`;
   - si no hay ninguna detección en todo el clip y la ausencia está confirmada (§4.4) ⇒ FALSE `OBJECT_NOT_FOUND`;
   - si no ⇒ UNKNOWN `NOT_VISIBLE_AT_END` (incluye manos tapando: PRD §9).
2. Mediana de `inside[zona]` sobre `V` ≥ θ_in ⇒ TRUE.
3. Mediana ≤ θ_out ⇒ FALSE `OUT_OF_ZONE`, con evidencia del fotograma clave y la zona en la que sí está (si alguna).
4. Entre ambos ⇒ UNKNOWN `BORDERLINE_POSITION`.

`at: during` en `[t(from), t(to)]` (con `t` = `t_hi` de los eventos): FALSE si hay un `remove` observado de esa zona en el intervalo; TRUE si cobertura VISIBLE ≥ 0,8, todas las lagunas puenteadas y mediana inside ≥ θ_in; UNKNOWN en otro caso (incluido evento `from` no ocurrido: `ANCHOR_EVENT_MISSING`).

### 4.4 `present_in_zone` y ausencia

TRUE si existe un tramo VISIBLE ≥ `presence_min_ms` con inside ≥ θ_in. Para FALSE se exige **ausencia confirmada**: (a) la segmentación global no está vacía (otros objetos sí se ven), (b) la calibración es `ALIGNED/RECALIBRATED`, (c) la zona no está ocluida por manos en la ventana final, y (d) el adaptador ejecutó un `AbsenceProbe` (re-sondeo del mismo prompt sobre 5 fotogramas finales) con `max_score < 0,3`, cuando ese mismo prompt detectó el objeto en la referencia con score ≥ 0,7. Si falta cualquiera ⇒ UNKNOWN `ABSENCE_UNCONFIRMED`. Justificación: el PRD exige a la vez detectar «falta un objeto» (error típico) y no producir FAIL por segmentación vacía; la condición (a)+(d) separa «SAM no funciona en este clip» de «el objeto no está».

### 4.5 `before` (precedencia por intervalos)

```python
def eval_before(ev1: Event|None, ev2: Event|None, ctx) -> Outcome:
    if ev1 and ev2:
        if ev1.t_hi < ev2.t_lo:  return TRUE(evidence=[ev1, ev2])
        if ev2.t_hi < ev1.t_lo:  return FALSE("ORDER_VIOLATED", evidence=[ev2, ev1])
        return UNKNOWN("ORDER_OVERLAP", missing=["separación temporal entre colocaciones"])
    if ev2 and not ev1:
        # B se colocó; ¿A estuvo observado sin colocarse hasta t_lo(B)?
        if ctx.only_initial_rest(A) and ctx.visible_coverage(A, 0, ev2.t_lo) >= coverage_min:
            return FALSE("FIRST_EVENT_MISSING_BEFORE_SECOND", evidence=[ev2, state(A at ev2.t_lo)])
        return UNKNOWN("ORDER_NOT_OBSERVED")
    if ev1 and not ev2:
        return UNKNOWN("EVENT_NOT_OCCURRED")       # la omisión la juzgan las reglas de posición
    return UNKNOWN("ORDER_NOT_OBSERVED")          # ninguno observado
```

- [DECISIÓN] El orden se decide por **separación estricta de intervalos**, no por comparar instantes puntuales. Colocaciones simultáneas (dos manos) o con lagunas solapadas ⇒ REVIEW. Esto hace la regla monótona respecto a la pérdida de fotogramas.
- [DECISIÓN] Si el segundo evento no ocurre, `before` queda REVIEW y no FAIL: no hay ningún evento que contradiga el orden, y la falta de B la reporta su regla de posición (aislamiento de causas, PRD §9). Si el procedimiento no tiene regla de posición para B, el compilador ya lo advirtió (§2.3).

### 4.6 Agregación global

```
si compuerta global activa       → REVIEW (con blocking_issue; UI: «sin veredicto»)
si ∃ regla habilitada FAIL        → FAIL
si ∃ regla habilitada REVIEW      → REVIEW
si todas PASS y n_habilitadas ≥ 1 → PASS
```

Las reglas deshabilitadas se reportan como `SKIPPED` y no participan. Precedencia FAIL > REVIEW (EP-05): es segura porque un FAIL nunca puede depender de un objeto con identidad no confirmada (compuerta §4.1).

### 4.7 Tabla de casos límite (PRD §9 y adicionales)

| Caso | Observación típica | Resultado por regla | Global |
|---|---|---|---|
| Vídeo sin objetos detectables | Ningún tracklet con ≥ 500 ms VISIBLE | Todas REVIEW `INSUFFICIENT_OBSERVATION` | REVIEW «sin veredicto», recomendar regrabar |
| Manos tapan objeto al final | `|V|/|W|` < 0,7 por `hand_overlap` | `in_zone_at end` REVIEW `NOT_VISIBLE_AT_END`; `before` puede seguir decidido | REVIEW (salvo otro FAIL) |
| Mismos componentes, orden incorrecto | place:B.t_hi < place:A.t_lo | `in_zone_at` PASS ×N; `before` FAIL `ORDER_VIOLATED` | FAIL |
| Orden correcto, objeto fuera de zona | place:B en zona None/otra, tras A | `before` PASS; `in_zone_at(B)` FAIL `OUT_OF_ZONE` | FAIL |
| Dos objetos casi idénticos | margen de asignación < δ (§5) | Reglas de ambos REVIEW `IDENTITY_UNCONFIRMED` hasta confirmación humana | REVIEW → re-evaluación tras confirmar |
| Solo se ve el final | Todos en `initial_rest` dentro de zona; 0 eventos `place` | `in_zone_at end` PASS; `before` REVIEW `ORDER_NOT_OBSERVED` | REVIEW |
| Cambio fuerte de cámara | Calibración `INCOMPATIBLE` | No se evalúan | REVIEW `CAMERA_INCOMPATIBLE`, pedir recalibración |
| Cámara movida a mitad del clip | Deriva > 0,02·diag | Reglas con zona REVIEW `CAMERA_MOVED` | REVIEW |
| Colocación simultánea A y B | Intervalos solapados | `before` REVIEW `ORDER_OVERLAP` | REVIEW |
| A colocado, B, A reajustado (≥ move_min) | primera: A<B; definitiva: B<A | `before` REVIEW `ORDER_AMBIGUOUS_REPLACEMENT` | REVIEW |
| Objeto falta del todo | Sin detección, probe < 0,3, otros visibles | `present_in_zone`/`in_zone_at` FAIL `OBJECT_NOT_FOUND` | FAIL |
| Segmentación vacía por fallo del modelo | Ningún objeto detectado | (= primera fila) | REVIEW, nunca PASS/FAIL |
| Objeto retirado de la mesa al final | Sale por el borde, visible | `in_zone_at end` FAIL `OBJECT_REMOVED` | FAIL |
| Edición posterior de reglas | Nueva `version` | Informes previos conservan su `(version, hash)` | — |
| Procedimiento no aprobado | `approved_by_user=false` | Rechazo al compilar | No se ejecuta |

---

## 5. Correspondencia de identidad entre clips

### 5.1 Estrategia

1. **Prompts por objeto confirmado.** En la ejecución, SAM recibe un prompt por objeto con la `description` confirmada (y alias propuestos por Muse Spark). Cada tracklet llega con `prompt_id` (S1). Esto ya separa la mayoría de los casos de objetos diferenciables.
2. **Agrupación intra-clip:** tracklets con el mismo `prompt_id` que no se solapan en el tiempo y cuya unión es espacialmente continua (fin→inicio ≤ `max_gap_ms` y ≤ 0,1·diag, o el siguiente empieza en el borde) se unen en una *pista de objeto*. Tracklets solapados del mismo prompt con score ≥ 0,5 ⇒ **candidatos competidores** (S9).
3. **Coste de asignación** objeto `o` ↔ pista candidata `p` (todo en `[0,1]`):
   `c = 0,35·(1 − prompt_match) + 0,40·d_Bhattacharyya(hsv_o, hsv_p) + 0,15·min(1, |ln(area_p/area_o)|/ln 2) + 0,10·min(1, |ln(aspect_p/aspect_o)|/ln 2)`
   con `prompt_match = 1` si la pista vino del prompt de `o`, `0` si no. Firmas HSV calculadas sobre píxeles enmascarados en fotogramas VISIBLE de score ≥ 0,7.
4. **Asignación óptima** por enumeración de permutaciones (≤ 4 objetos ⇒ ≤ 24 asignaciones; sin SciPy).
5. **Muse Spark como señal, no como juez.** Solo si hay ambigüedad (5.2), el orquestador puede pedir a Muse Spark que empareje recortes con descripciones; su respuesta entra como `IdentityHint(source="muse", mapping, confidence)` cacheada y registrada. El motor la usa para **ordenar** las opciones mostradas al humano, nunca para cerrar una ambigüedad por sí sola. Justificación: PRD §8 exige confirmación si es ambiguo y §11 prohíbe delegar el veredicto en el LLM; una identidad errónea genera FAIL falsos.

[DECISIÓN] **La posición final (zona) no se usa como señal de identidad.** El PRD menciona «verificación de zona», pero usarla para asignar identidad es circular: favorecería que cada objeto «esté en su zona» y ocultaría precisamente el error «A en la zona de B». La zona solo se usa *después*, como comprobación de coherencia: si dos objetos con firmas cercanas (d < 0,25) aparecen intercambiados respecto a la referencia, se marca la asignación como ambigua.

### 5.2 Umbrales de ambigüedad

| Condición | Estado | Efecto |
|---|---|---|
| Coste de la mejor asignación para `o` ≤ 0,45 y margen frente a la segunda mejor asignación global ≥ 0,15 | `AUTO_CONFIRMED` | Se evalúan reglas |
| Margen < 0,15, o coste > 0,45, o candidatos competidores sin resolver, o intercambio sospechoso (§5.1) | `NEEDS_CONFIRMATION` | Reglas del objeto REVIEW `IDENTITY_UNCONFIRMED`; `RunReport.identity_requests` lista recortes candidatos |
| Ningún candidato con coste ≤ 0,7 | `NOT_FOUND` | Tratado como ausencia candidata (§4.4) |

La confirmación humana entra como `IdentityHint(source="user")`, que fija la asignación; `verify_run` se re-ejecuta (barato: no hay llamadas a modelo) y el informe registra quién confirmó.

### 5.3 Objetos indistinguibles en la referencia

Al compilar, si dos objetos tienen `d_Bhattacharyya < 0,20` y ratio de área ∈ [0,8, 1,25], se marcan `indistinguishable_from` y Rule Studio pide una descripción diferenciadora. Si el usuario acepta igualmente, toda ejecución pedirá confirmación de identidad para ese par (PRD §9 «dos objetos casi idénticos»).

---

## 6. Evidencia y registro de auditoría

### 6.1 `RunReport` (`ghostshift.report/1`)

```python
class Evidence(BaseModel):
    kind: Literal["event", "state", "absence", "gap", "calibration"]
    object_id: str | None; zone_id: str | None
    track_ids: list[str]                 # tracklets del clip de ejecución
    t_ms: int                            # instante mostrado (t_hi para eventos)
    t_interval_ms: tuple[int, int] | None
    frames: list[int]                    # fotogramas que soportan la afirmación
    keyframe: int                        # fotograma a resaltar en la UI
    mask_rle: RLE | None; bbox: tuple[float,float,float,float] | None
    zone_polygon_exec: list[tuple[float,float]] | None   # zona ya transformada
    metrics: dict[str, float]            # inside, score, visible_ratio, hand_overlap…
    flags: list[str]                     # timing_uncertain, identity_suspect…

class RuleResult(BaseModel):
    rule_id: str; rule_text_es: str
    verdict: Literal["PASS", "FAIL", "REVIEW", "SKIPPED"]
    reason_code: str                     # enumerado cerrado (§4)
    explanation_es: str                  # plantilla determinista por reason_code
    evidence: list[Evidence]; missing: list[str]   # qué dato faltó (REVIEW)

class RunReport(BaseModel):
    schema_version: Literal["ghostshift.report/1"]
    run_id: str; global_verdict: Literal["PASS", "FAIL", "REVIEW"]
    blocking_issue: str | None
    procedure_ref: ProcedureRef          # id, version, content_hash
    rules: list[RuleResult]
    events: list[Event]                  # línea de tiempo completa (también los no usados)
    identity: IdentityResolution; calibration: CalibrationResult
    identity_requests: list[IdentityRequest]
    provenance: Provenance               # ver 6.2
```

[DECISIÓN] Las explicaciones en español salen de **plantillas por `reason_code`** («B se colocó en t=4,2 s, antes que A (t=7,9 s)»), no de un LLM. Muse Spark puede reformularlas en la UI, pero el texto canónico es el de la plantilla.

### 6.2 Auditoría

- Archivo **JSONL append-only** por sesión (`audit/<session>.jsonl`), una línea por hecho: `procedure_compiled`, `model_call` (modelo, versión, `request_id`, latencia, `cache_hit`, hash de prompts), `trackset_ingested` (sha256), `calibration`, `identity_resolved` (fuente: auto/user/muse), `verdict`.
- `Provenance` en cada informe: `engine_version` (semver + git sha), `params_hash`, `procedure.content_hash`, `trackset_sha256`, `video_sha256`, `identity_hints_hash`.
- **Reproducción:** `ghostshift-engine replay <run_id>` reconstruye el informe desde el `TrackSet` cacheado y compara hash; cualquier diferencia es un fallo de determinismo. Esto es la prueba ante el jurado de que no hay resultados precalculados por vídeo (PRD §4.2, §15).
- Privacidad (PRD §12): el log guarda hashes y metadatos, no fotogramas; los recortes de evidencia viven con la sesión y se borran con ella.

---

## 7. Estrategia de pruebas

### 7.1 Herramientas

`pytest` + `hypothesis` (pruebas de propiedades). Ningún test del motor llama a modelos ni a red; un test de importación falla si `ghostshift_engine` importa `requests`, `httpx`, `urllib3` o `socket`.

### 7.2 Generador de pistas sintéticas (`synth.py`)

DSL de escenario → `TrackSet` + verdad de terreno:

```python
Scenario(
  fps=10, duration_ms=20000, size=(160, 90),
  objects={"A": Rect(w=.06, h=.05, start=(.15, .80)), "B": Rect(w=.05, h=.05, start=(.30, .80))},
  zones=std_zones("left", "right"),
  actions=[Move("A", to="left", t0=3000, dur=1200), Move("B", to="right", t0=7000, dur=1000)],
  occlusions=[Hand(over="A", t0=18500, t1=20000)],     # genera también la pista aux:hand
  dropouts=[Dropout("B", t0=7200, t1=7800)],
  noise=Noise(centroid_sigma=.003, score_mu=.85, score_sigma=.05, id_switch_prob=.0),
  camera=Shift(dx=.0, dy=.0, rot_deg=0),
  start_ms=0,                                          # >0 simula «solo se ve el final»
).render() -> (TrackSet, GroundTruth(events=[…], expected={"R1": "PASS", …}))
```

Las máscaras se rasterizan como rectángulos/elipses a baja resolución y se codifican en RLE, para ejercitar el camino completo `features → events → rules`. Los movimientos usan trayectorias con levantamiento (escala aparente y mano encima) para simular agarres. `id_switch_prob` fragmenta tracklets para probar la agrupación.

### 7.3 Tests unitarios (por módulo)

- `geometry`: RLE ida/vuelta; `inside` de rectángulos conocidos; transformación de polígonos.
- `events`: una colocación limpia ⇒ 1 `place` con `t_hi − t_real ∈ [stable_ms, stable_ms+100]`; reajuste < `move_min` ⇒ 0 eventos; histéresis en el borde (oscilación de inside 0,5↔0,55) ⇒ 0 `remove`; laguna corta en reposo ⇒ puente; laguna con desplazamiento ⇒ evento `timing_uncertain`; entrada desde fuera de plano.
- `rules`/`verdict`: una prueba por fila de la tabla §4.7, construida con `synth.py`.
- `identity`: 3 objetos de colores distintos con IDs barajados ⇒ asignación correcta; dos objetos con la misma firma ⇒ `NEEDS_CONFIRMATION`; intercambio de zonas con firmas parecidas ⇒ ambiguo.
- `contracts`: migración v1→v2 del ejemplo literal del PRD §8; rechazo de ciclos en `before`.
- `adapter` (fuera del motor): golden tests con `fixtures/sam_raw/` del día 1.

### 7.4 Propiedades invariantes (hypothesis sobre escenarios aleatorios válidos)

| ID | Propiedad |
|---|---|
| P1 | **Nunca PASS ni FAIL con segmentación vacía**: `TrackSet` sin tracklets de objeto ⇒ global REVIEW y todas las reglas REVIEW |
| P2 | **Monotonía de REVIEW**: añadir lagunas/oclusiones o bajar scores solo puede cambiar PASS→REVIEW o FAIL→REVIEW; nunca PASS↔FAIL |
| P3 | Todo FAIL tiene ≥ 1 `Evidence` con `frames` no vacíos y fotogramas VISIBLE |
| P4 | Invariancia a permutación/renombrado de `track_id` |
| P5 | Invariancia al ritmo: escalar los tiempos de las acciones ×[0,6, 1,8] (manteniendo pausas ≥ `stable_ms`) no cambia veredictos |
| P6 | Invariancia al fps: el mismo escenario a 8, 10 y 15 fps produce los mismos veredictos |
| P7 | Desplazamiento de cámara dentro de `ALIGNED` con calibración aplicada ⇒ mismos veredictos |
| P8 | Determinismo: dos ejecuciones ⇒ `RunReport` idéntico (hash) |
| P9 | Deshabilitar una regla no cambia el veredicto de las demás |
| P10 | Agregación: global == función de §4.6 sobre los veredictos por regla |
| P11 | «Mismo estado final, orden distinto»: para todo par de escenarios que solo difieren en el orden de `Move`, las reglas `in_zone_at end` coinciden y al menos una `before` difiere |

P2 es la más delicada; si hypothesis encuentra un contraejemplo, se corrige el detector (no se relaja la propiedad).

### 7.5 Evaluación del dataset de 12 ejecuciones (PRD §13)

1. **Antes de ejecutar nada**, se escribe `dataset/manifest.yaml`: por clip, procedimiento, tipo (correcto / error tipo X / insuficiente), veredicto global esperado, veredicto esperado por regla e instantes de colocación anotados a mano (±200 ms). Se versiona en git (commit anterior a la primera evaluación).
2. Distribución recomendada de los 6 errores (3 por procedimiento): orden invertido con mismo estado final (≥ 1 por procedimiento, PRD §13), objeto en zona equivocada, objeto ausente, dos objetos intercambiados de zona, objeto retirado al final. Insuficientes (2): manos sobre la zona al final; grabación que empieza tras las colocaciones.
3. Los `TrackSet` se cachean tras la única llamada a SAM; `ghostshift-engine eval dataset/` corre offline y emite: matriz 3×3 global (esperado × obtenido), matriz por regla, error temporal de eventos (mediana y p90), recall/precisión de eventos `place`, y `params_hash`.
4. **Regla anti-sobreajuste:** cualquier cambio de parámetros tras ver resultados se registra con motivo, cambia `params_hash` y obliga a re-evaluar los 12; el segundo procedimiento no puede motivar cambios de parámetros (es el conjunto de generalización). Se reportan honestamente los resultados de la primera evaluación y los de la final.
5. Criterio de éxito (PRD §13): 4/4 PASS, ≥ 5/6 FAIL con la regla causante correcta, 2/2 REVIEW, **0 FAIL en clips correctos o insuficientes** (requisito propio más estricto: un FAIL falso es peor que un REVIEW), error temporal p90 ≤ 500 ms en eventos usados como evidencia.

---

## 8. Estructura del motor

[DECISIÓN] **Python 3.11 puro**, `pydantic` v2 para contratos (validación + exportación de JSON Schema para el frontend), `numpy` para máscaras, `opencv-python-headless` solo en `calibration.py`. Sin SciPy, sin red. Justificación: el backend y los SDK de modelos serán con mayor probabilidad Python; numpy cubre RLE y rasterizado; el tamaño del problema (≤ 4 objetos, ≤ 600 fotogramas) no requiere más rendimiento (objetivo: `verify_run` < 1 s por clip de 60 s).

```
engine/
  pyproject.toml
  ghostshift_engine/
    __init__.py          # API pública: compile_procedure, propose_from_reference, verify_run
    version.py
    contracts/
      tracks.py          # TrackSet, Tracklet, FrameObs, AbsenceProbe
      procedure.py       # esquema v2, migración v1→v2, validación
      params.py          # EngineParams (frozen) + defaults + hash
      results.py         # Event, Evidence, RuleResult, RunReport, reason codes
    geometry.py          # RLE, rasterizado de polígonos, inside, transformaciones
    calibration.py       # T_ref→exec, deriva intra-clip (OpenCV)
    features.py          # rasgos y obs_state por fotograma
    identity.py          # agrupación de tracklets, costes, asignación, ambigüedad
    events.py            # máquina de estados place/remove, lagunas, ocurrencias
    rules.py             # registro tipo → evaluador (añadir tipo = añadir función)
    verdict.py           # compuertas, Kleene, agregación, regla de oro de FAIL
    explain.py           # plantillas es-ES por reason_code
    audit.py             # JSONL, provenance, replay
    synth.py             # generador de escenarios (también para la demo de tests)
    cli.py               # verify | replay | eval
  tests/{unit,property,fixtures}/
```

`propose_from_reference(trackset_ref)` reutiliza `features` + `events` sobre el clip de referencia para producir zonas (§2.4) y la cadena de `place` observada; el orquestador la cruza con la propuesta de Muse Spark y marca como **hipótesis** cualquier orden propuesto por el LLM que contradiga los eventos observados (EP-02).

---

## 9. Riesgos residuales y criterios de no-go (29–30 oct)

### 9.1 Riesgos residuales

| Riesgo | Por qué persiste | Mitigación en este diseño |
|---|---|---|
| SAM no ofrece tracking temporal ni prompts de texto en el API | No verificado (S1, S2) | Adaptador con asociación IoU y prompts por caja; el motor no cambia |
| Fecha de evento sesgada por la mano | La estabilidad se mide tras retirar la mano | Se fecha con intervalo `[t_lo, t_hi]`; el orden usa separación de intervalos |
| Colocaciones por deslizamiento corto (< `move_min`) | Indistinguibles de un reajuste | Guía de grabación; `move_min` medido el día 29 |
| Objetos apilados u ocluidos entre sí | Fuera de alcance P2, pero aparecerá | `frag_ratio` ⇒ OCCLUDED ⇒ REVIEW, no FAIL |
| Exceso de REVIEW (producto «tímido») | Decisiones conservadoras (§3.6, §4.5) | Medir tasa de REVIEW en clips correctos; objetivo 0/4 |
| Zonas derivadas demasiado estrictas | Una sola referencia | Margen 30 %; `BORDERLINE_POSITION` ⇒ REVIEW en vez de FAIL |
| Firmas de color sensibles a iluminación | HSV sin normalizar | Histograma con V grueso (4 bins); confirmación humana como red |

### 9.2 Criterios medibles de go / no-go

Medidos sobre ≥ 3 pares reales (referencia + ejecución) grabados el 29 oct, con instantes anotados a mano:

| Fecha | Métrica | Go | No-go / acción |
|---|---|---|---|
| 29 oct | API SAM devuelve máscaras por fotograma con identidad intra-clip (o asociable por IoU) a ≥ 5 fps efectivos | Sí | **No-go del motor de secuencias** si no hay salida temporal utilizable ⇒ replantear (PRD §13) |
| 29 oct | Cobertura VISIBLE de objetos en tramos sin mano | ≥ 85 % | < 70 % ⇒ cambiar encuadre/iluminación antes de seguir |
| 29 oct | Recall de colocaciones (evento con `t_hi` a ≤ 500 ms del anotado) | ≥ 90 % | < 75 % ⇒ **conditional go** del PRD: solo presencia/posición, sin vender orden |
| 29 oct | Colocaciones falsas por clip | ≤ 0,5 de media | > 1 ⇒ igual que la fila anterior |
| 30 oct | Identidad automática correcta (`AUTO_CONFIRMED` y correcta) | ≥ 90 % de objetos | < 70 % ⇒ confirmación humana obligatoria en cada ejecución (aceptable para demo, declarado) |
| 30 oct | Identidad `AUTO_CONFIRMED` **incorrecta** | 0 | > 0 ⇒ subir margen δ a 0,25 y re-medir; si persiste, confirmación siempre |
| 30 oct | Suite sintética: tests §7.3 + propiedades P1–P11 | 100 % verde | Cualquier fallo en P1/P2/P3 bloquea la integración con UI |
| 30 oct | Veredicto correcto en los 3 pares reales sin cambiar parámetros entre clips | 3/3 (REVIEW aceptado en el insuficiente) | Un FAIL falso en un clip correcto ⇒ no avanzar al 31 oct sin diagnosticar |
| 30 oct | Latencia SAM por clip de 30 s | ≤ 3 min | > 5 min ⇒ bajar a 5 fps y clips ≤ 20 s (parámetro global, re-medir P6) |

Si el 30 oct el recall de colocaciones no alcanza el umbral, el producto se presenta como verificador de **estados** (presencia y posición) y la regla `before` se oculta en Rule Studio, sin describir GhostShift como verificador de secuencias (PRD §13, §14).
