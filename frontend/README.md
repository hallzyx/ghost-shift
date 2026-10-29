# GhostShift — Frontend

React 18 + Vite + TypeScript SPA (no SSR). It implements the Teach → Review rules → Verify → Result flow against the contract in `docs/API_CONTRACT.md`. The design is described in `docs/DESIGN.md`. The user-facing strings are currently in Spanish.

## Requirements

- Node.js 18 or later (tested with Node 22).
- For real mode: the FastAPI backend at `http://localhost:8000` (see `backend/`).

## Installation

```bash
cd frontend
npm install
```

## Run against the real backend

```bash
# 1) start the backend on :8000 (see the root README or docs/TECH_SPEC.md)
# 2) in another terminal:
npm run dev            # http://localhost:5173
```

The browser only talks to `/api/*`; Vite forwards those requests to the backend, stripping the `/api` prefix (`vite.config.ts`). The backend's `video_url` and `frame_url` are also served through `/api`.

If the backend is on another host or port:

```bash
VITE_BACKEND_URL=http://127.0.0.1:9000 npm run dev
```

On Windows (PowerShell): `$env:VITE_BACKEND_URL="http://127.0.0.1:9000"; npm run dev`.

The frontend does **not** need, and must not receive, API keys: all model calls happen in the backend.

## Mock mode (no backend)

```bash
npm run dev:mock       # equivalent to VITE_MOCK=1
```

- Simulated responses **in the browser** that respect the contract: stages that advance (~8 s), a draft with a disabled hypothesis and uncertainties, and sample runs that give PASS («Ejecución correcta»), FAIL («Orden invertido») and REVIEW («Mano tapando una pieza»). The evidence frames are placeholder SVGs labeled «Fotograma simulado».
- To see the error state with «Reintentar» (Retry), upload a file whose name contains `error` (e.g. `error.mp4`): the analysis will fail once.
- The interface shows the «Modo demo simulado» (simulated demo mode) badge and the call log shows `(simulado)`.
- The mock lives isolated in `src/mock/`. In any build without `VITE_MOCK=1`, `vite.config.ts` replaces that module with an empty stub: neither its code nor its videos enter the real bundle. It is never enabled by default.
- Its state is stored in `localStorage` (`ghostshift.mock.v1`); clear it with «Borrar mi sesión y datos» (Delete my session and data).

## Scripts

| Script | What it does |
|---|---|
| `npm run dev` | Development server with the `/api` → backend proxy |
| `npm run dev:mock` | Development server with the simulated backend |
| `npm run build` | `tsc -b` (strict TypeScript) + production build in `dist/` |
| `npm run preview` | Serves `dist/` (also with the `/api` proxy) |
| `npm run typecheck` | Type checking only |

## Structure

```
src/
  api/          client.ts (typed client for the contract), types.ts
  components/   Layout, Stepper, VideoPlayer, ZoneOverlay, RuleCard, ObjectCard,
                EvidenceFrame, StageProgress, DropZone, Consent, ui (primitives)
  context/      AppContext (session and consent, toasts, theme, current step)
  lib/          formatting, rules (text and cycle validation), polling
  pages/        Home, Teach (A), Procedure (B analysis / C Rule Studio), Verify (D), Run (E), Audit
  mock/         simulated backend (only with VITE_MOCK=1)
  styles/       tokens.css, base.css, components.css, pages.css
```

Notes on the contract and assumptions: `NOTES.md`.
