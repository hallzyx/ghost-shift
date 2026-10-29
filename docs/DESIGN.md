# GhostShift — Interface design

UX/UI decisions for the frontend (`frontend/`). Complements `docs/PRD.md` §10 and `docs/TECH_SPEC.md` §6. The user-facing strings in the interface are currently in Spanish; the labels quoted below are shown as they appear in the UI, with a translation where useful.

## Principles

1. **One primary action per screen.** It is the only blue pill button visible: «Enseñar nuevo procedimiento» (Teach a new procedure), «Analizar video» (Analyze video), «Guardar y aprobar procedimiento» (Save and approve procedure), «Verificar ejecución» (Verify run) and «Verificar otra ejecución» (Verify another run). The other actions are secondary (gray) or links.
2. **Models propose, the user approves, the engine decides.** This is repeated on the start screen, in the Rule Studio header («La IA propone; tú decides la norma» — the AI proposes; you decide the rule) and in «Cómo llegamos a este resultado» (How we reached this result).
3. **Honesty.** Hypotheses arrive disabled, with a dashed amber border and the label «Hipótesis (no respaldada por SAM)» (Hypothesis, not backed by SAM). REVIEW is explained as «insufficient observation, not a failure». Mock mode is announced in the top bar and in the call log. There is no talk of certification or real time.
4. **Progressive disclosure.** Rule editing expands per card. The `sam_prompt` lives under «Cómo lo busca la IA» (How the AI looks for it). Evidence for passing rules is collapsed; evidence for FAIL/REVIEW is always visible.
5. **Never color alone.** Verdicts combine an icon, a word (PASS/FAIL/REVIEW/SKIPPED) and text («No cumple», not met). Timeline marks change shape: filled circle = confirmed, dashed circle = approximate or Muse-only, diamond = failure or doubt.

## Flow and screens

A fixed 4-step stepper in the top bar (on mobile: «Paso 2 de 4 · Revisar reglas» — Step 2 of 4 · Review rules).

| Route | Screen | Step |
|---|---|---|
| `/` | My procedures; if empty, a landing page with «Cómo funciona» (How it works) | — |
| `/ensenar` | A. Teach: drag and drop, requirements, examples, name, client-side validation | 1 |
| `/procedimientos/:pid` | B. Staged analysis (polling every 1.5 s) and, when finished, C. Rule Studio | 1 → 2 |
| `/procedimientos/:pid/verificar` | D. Verify (blocked and explained if there is no approved version) | 3 |
| `/ejecuciones/:rid` | Verification progress and E. Result | 3 → 4 |
| `/auditoria` | Log of model calls | — |

**Rule Studio.** On the left, a sticky video with the zones drawn on top and a timeline with the events from `draft.timeline`; a click jumps to the instant. «Editar zonas» (Edit zones) lets you move the whole zone or drag its vertices, also with the keyboard (arrows, Shift for a large step). On the right, in this order: objects (editable name and an English search term in the advanced section), rules, hypotheses and uncertainties. A fixed bottom bar shows «Cambios sin guardar» (Unsaved changes) and holds the primary action. Leaving with pending changes asks for confirmation (router blocking and `beforeunload`). Editing an approved version warns that version N+1 will be created.

**Result.** A verdict block with a brand ring, counters per status and the two exit actions. Below there are two columns: on one side the run video (with «Comparar con referencia», Compare with reference) and the combined timeline; on the other, the rules ordered FAIL → REVIEW → PASS → SKIPPED, with their explanation (`reason_es`) and their frames. Clicking a frame jumps the video to `t_ms`.

## Tokens (`frontend/src/styles/tokens.css`)

Inspired by the feel of Meta's interfaces, without using brand assets. Own logo: a blue ghost with an offset gradient «double» (the reference and the run).

- **Color:** primary `#0866FF` (hover `#0A5AE0`, pressed `#0753CC`, tint `#E7F0FF`); text `#1C1E21` and `#65676B`; background `#F0F2F5`; surface `#FFF`; borders `#CED0D4` and `#E4E6EB`; success `#31A24C`; error `#E41E3F`; warning/REVIEW `#F7B928` with dark text (`#6B4E00` on tint). Dark mode: `#18191A`, `#242526`, `#3A3B3C`, text `#E4E6EB` and `#B0B3B8`. Status text uses darker `*-text` variants (or lighter in dark mode) to meet AA on its tint.
- **Brand gradient** (blue → violet → cyan): only on the «analyzing» ring, on the live progress bar, on the verdict ring and on the landing headline.
- **Typography:** local Inter (`@fontsource/inter`, weights 400–700) with a system fallback. Scale 12/13/15/17/20/24/32.
- **Shape:** cards with a 12 px radius and a very soft shadow; pill buttons; inputs with an 8 px radius; spacing in multiples of 4.
- **Motion:** 150–200 ms with `cubic-bezier(.2,0,0,1)`. Animations are disabled under `prefers-reduced-motion`.
- **Theme:** follows `prefers-color-scheme` and can be forced to Light or Dark from the menu (`data-theme`).
- **Object color:** inferred from the color word in `sam_prompt` or the description («blue», «rojo»…), with a fallback palette. The text on top is chosen by luminance (white or near black).

## Components

`VideoPlayer` (custom controls, track with marks and ranges, imperative `seek(t_ms)`), `ZoneOverlay` (normalized polygons in SVG and HTML handles), `RuleCard`, `ObjectCard`, `EvidenceFrame`, `StageProgress`, `DropZone`, `VerdictBadge`/`StatusBadge`/`OriginBadge`, and primitives (`Button`, `Badge`, `Callout`, `Modal` with a focus trap, `Toggle` with `role="switch"`, `InfoTip`, `Skeleton`, `EmptyState`).

## Accessibility

- Visible focus (double blue ring), a «Skip to content» link and a logical tab order. Modals trap focus and close with Esc.
- `aria-live` on staged progress, on the save state and on notices. The progress bar has `role="progressbar"`.
- The video track is a `role="slider"` (arrows, Home/End, space). Each mark is a button with its description.
- AA contrast for text. Verdicts and hypotheses never depend on color alone.
- Responsive: desktop is the primary target; on tablet and mobile (≥ 360 px) everything collapses to one column, the stepper compacts and the action bar takes the full width. No horizontal overflow.
- Empty, loading (skeletons), error with «Reintentar» (Retry) and 404 states on all screens.

## Permanent notices

The footer shows on every screen «Prototipo de investigación — no apto para controles críticos o de seguridad» (not suitable for critical or safety controls) and the credit «Con modelos Muse Spark y SAM 3.1 de la API de Meta» (With Muse Spark and SAM 3.1 models from the Meta API), with links to Call log, Privacy and «Borrar mi sesión y datos» (Delete my session and data). Consent is requested in a modal before the first upload.
