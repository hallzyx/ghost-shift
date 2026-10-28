# GhostShift — Diseño de la interfaz

Decisiones de UX/UI del frontend (`frontend/`). Complementa `docs/PRD.md` §10 y `docs/TECH_SPEC.md` §6.

## Principios

1. **Una acción primaria por pantalla.** Es el único botón pill azul visible: «Enseñar nuevo procedimiento», «Analizar video», «Guardar y aprobar procedimiento», «Verificar ejecución» y «Verificar otra ejecución». El resto de acciones son secundarias (gris) o enlaces.
2. **Los modelos proponen, el usuario aprueba, el motor decide.** Esto se repite en la pantalla de inicio, en el encabezado del Rule Studio («La IA propone; tú decides la norma») y en «Cómo llegamos a este resultado».
3. **Honestidad.** Las hipótesis llegan desactivadas, con borde discontinuo ámbar y la etiqueta «Hipótesis (no respaldada por SAM)». REVIEW se explica como «observación insuficiente, no es un fallo». El modo mock se anuncia en la barra superior y en el registro de llamadas. No se habla de certificación ni de tiempo real.
4. **Revelación progresiva.** La edición de reglas se despliega por tarjeta. El `sam_prompt` vive en el apartado «Cómo lo busca la IA». La evidencia de las reglas que cumplen está plegada; la de FAIL/REVIEW, siempre visible.
5. **Nunca solo color.** Los veredictos combinan icono, palabra (PASS/FAIL/REVIEW/OMITIDA) y texto («No cumple»). Las marcas de la línea de tiempo cambian de forma: círculo relleno = confirmado, círculo discontinuo = aproximado o solo Muse, rombo = incumplimiento o duda.

## Flujo y pantallas

Stepper fijo de 4 pasos en la barra superior (en móvil: «Paso 2 de 4 · Revisar reglas»).

| Ruta | Pantalla | Paso |
|---|---|---|
| `/` | Mis procedimientos; si está vacía, portada con «Cómo funciona» | — |
| `/ensenar` | A. Enseñar: arrastrar y soltar, requisitos, ejemplos, nombre, validación en cliente | 1 |
| `/procedimientos/:pid` | B. Análisis por etapas (polling cada 1,5 s) y, al terminar, C. Rule Studio | 1 → 2 |
| `/procedimientos/:pid/verificar` | D. Verificar (bloqueado y explicado si no hay versión aprobada) | 3 |
| `/ejecuciones/:rid` | Progreso de verificación y E. Resultado | 3 → 4 |
| `/auditoria` | Registro de llamadas a modelos | — |

**Rule Studio.** A la izquierda, un video fijo (sticky) con las zonas dibujadas encima y una línea de tiempo con los eventos de `draft.timeline`; un clic salta al instante. «Editar zonas» permite mover la zona entera o arrastrar sus vértices, también con teclado (flechas, Mayús para paso grande). A la derecha están, por este orden: objetos (nombre editable y búsqueda en inglés en el apartado avanzado), reglas, hipótesis e incertidumbres. Una barra inferior fija indica «Cambios sin guardar» y contiene la acción primaria. Salir con cambios pendientes pide confirmación (bloqueo del router y `beforeunload`). Editar una versión aprobada avisa de que se creará la versión N+1.

**Resultado.** Un bloque de veredicto con anillo de marca, contadores por estado y las dos acciones de salida. Debajo hay dos columnas: el video de la ejecución (con «Comparar con referencia») y la línea de tiempo combinada a un lado; las reglas ordenadas FAIL → REVIEW → PASS → OMITIDA, con su explicación (`reason_es`) y sus fotogramas, al otro. Un clic en un fotograma salta el video a `t_ms`.

## Tokens (`frontend/src/styles/tokens.css`)

Inspirados en la sensación de las interfaces de Meta, sin usar activos de marca. Logotipo propio: un fantasma azul con un «doble» desplazado en degradado (la referencia y la ejecución).

- **Color:** primario `#0866FF` (hover `#0A5AE0`, pulsado `#0753CC`, tinte `#E7F0FF`); texto `#1C1E21` y `#65676B`; fondo `#F0F2F5`; superficie `#FFF`; bordes `#CED0D4` y `#E4E6EB`; éxito `#31A24C`; error `#E41E3F`; aviso/REVIEW `#F7B928` con texto oscuro (`#6B4E00` sobre tinte). Modo oscuro: `#18191A`, `#242526`, `#3A3B3C`, texto `#E4E6EB` y `#B0B3B8`. Los textos de estado usan variantes `*-text` más oscuras (o más claras en oscuro) para cumplir AA sobre su tinte.
- **Degradado de marca** (azul → violeta → cian): solo en el anillo de «analizando», en la barra de progreso viva, en el anillo del veredicto y en el titular de la portada.
- **Tipografía:** Inter local (`@fontsource/inter`, pesos 400–700) con respaldo del sistema. Escala 12/13/15/17/20/24/32.
- **Forma:** tarjetas con radio de 12 px y sombra muy suave; botones pill; inputs con radio de 8 px; espaciado en múltiplos de 4.
- **Movimiento:** 150–200 ms con `cubic-bezier(.2,0,0,1)`. Con `prefers-reduced-motion` se desactivan las animaciones.
- **Tema:** sigue `prefers-color-scheme` y se puede forzar a Claro u Oscuro desde el menú (`data-theme`).
- **Color de objeto:** se deduce de la palabra de color en `sam_prompt` o la descripción («blue», «rojo»…), con una paleta de respaldo. El texto encima se elige por luminancia (blanco o casi negro).

## Componentes

`VideoPlayer` (controles propios, pista con marcas y rangos, `seek(t_ms)` imperativo), `ZoneOverlay` (polígonos normalizados en SVG y tiradores HTML), `RuleCard`, `ObjectCard`, `EvidenceFrame`, `StageProgress`, `DropZone`, `VerdictBadge`/`StatusBadge`/`OriginBadge`, y primitivas (`Button`, `Badge`, `Callout`, `Modal` con trampa de foco, `Toggle` con `role="switch"`, `InfoTip`, `Skeleton`, `EmptyState`).

## Accesibilidad

- Foco visible (anillo azul doble), enlace «Saltar al contenido» y orden de tabulación lógico. Los modales atrapan el foco y se cierran con Esc.
- `aria-live` en el progreso por etapas, en el estado de guardado y en los avisos. La barra de progreso tiene `role="progressbar"`.
- La pista del video es un `role="slider"` (flechas, Inicio/Fin, espacio). Cada marca es un botón con su descripción.
- Contraste AA en texto. Los veredictos y las hipótesis nunca dependen solo del color.
- Responsive: escritorio como objetivo principal; en tablet y móvil (≥ 360 px) todo pasa a una columna, el stepper se compacta y la barra de acción ocupa el ancho completo. No hay desbordamiento horizontal.
- Estados vacío, carga (skeletons), error con «Reintentar» y 404 en todas las pantallas.

## Avisos permanentes

El pie de página muestra en todas las pantallas «Prototipo de investigación — no apto para controles críticos o de seguridad» y la mención «Con modelos Muse Spark y SAM 3.1 de la API de Meta», con enlaces a Registro de llamadas, Privacidad y «Borrar mi sesión y datos». El consentimiento se pide en un modal antes de la primera subida.
