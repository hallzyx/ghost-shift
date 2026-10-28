# GhostShift — Frontend

SPA en React 18 + Vite + TypeScript (sin SSR). Implementa el recorrido Enseñar → Revisar reglas → Verificar → Resultado contra el contrato de `docs/API_CONTRACT.md`. El diseño está descrito en `docs/DESIGN.md`.

## Requisitos

- Node.js 18 o superior (probado con Node 22).
- Para el modo real: el backend FastAPI en `http://localhost:8000` (ver `backend/`).

## Instalación

```bash
cd frontend
npm install
```

## Ejecutar contra el backend real

```bash
# 1) arranca el backend en :8000 (ver backend/README o docs/TECH_SPEC.md)
# 2) en otra terminal:
npm run dev            # http://localhost:5173
```

El navegador solo habla con `/api/*`; Vite reenvía esas peticiones al backend quitando el prefijo `/api` (`vite.config.ts`). Los `video_url` y `frame_url` del backend se sirven también a través de `/api`.

Si el backend está en otro host o puerto:

```bash
VITE_BACKEND_URL=http://127.0.0.1:9000 npm run dev
```

En Windows (PowerShell): `$env:VITE_BACKEND_URL="http://127.0.0.1:9000"; npm run dev`.

El frontend **no** necesita ni debe recibir claves de API: todas las llamadas a modelos ocurren en el backend.

## Modo mock (sin backend)

```bash
npm run dev:mock       # equivale a VITE_MOCK=1
```

- Respuestas simuladas **en el navegador** que respetan el contrato: etapas que avanzan (~8 s), un borrador con hipótesis desactivada e incertidumbres, y ejecuciones de ejemplo que dan PASS («Ejecución correcta»), FAIL («Orden invertido») y REVIEW («Mano tapando una pieza»). Los fotogramas de evidencia son SVG de placeholder marcados «Fotograma simulado».
- Para ver el estado de error con «Reintentar», sube un archivo cuyo nombre contenga `error` (p. ej. `error.mp4`): el análisis fallará una vez.
- La interfaz muestra el distintivo «Modo demo simulado» y el registro de llamadas indica `(simulado)`.
- El mock vive aislado en `src/mock/`. En cualquier build sin `VITE_MOCK=1`, `vite.config.ts` sustituye ese módulo por un stub vacío: ni su código ni sus videos entran en el bundle real. Nunca se activa por defecto.
- Su estado se guarda en `localStorage` (`ghostshift.mock.v1`); bórralo con «Borrar mi sesión y datos».

## Scripts

| Script | Qué hace |
|---|---|
| `npm run dev` | Servidor de desarrollo con proxy `/api` → backend |
| `npm run dev:mock` | Servidor de desarrollo con el backend simulado |
| `npm run build` | `tsc -b` (TypeScript estricto) + build de producción en `dist/` |
| `npm run preview` | Sirve `dist/` (también con proxy `/api`) |
| `npm run typecheck` | Solo comprobación de tipos |

## Estructura

```
src/
  api/          client.ts (cliente tipado del contrato), types.ts
  components/   Layout, Stepper, VideoPlayer, ZoneOverlay, RuleCard, ObjectCard,
                EvidenceFrame, StageProgress, DropZone, Consent, ui (primitivas)
  context/      AppContext (sesión y consentimiento, toasts, tema, paso actual)
  lib/          formato, reglas (texto y validación de ciclos), polling
  pages/        Home, Teach (A), Procedure (B análisis / C Rule Studio), Verify (D), Run (E), Audit
  mock/         backend simulado (solo con VITE_MOCK=1)
  styles/       tokens.css, base.css, components.css, pages.css
```

Notas sobre el contrato y supuestos: `NOTES.md`.
