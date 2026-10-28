# GhostShift

**Enséñale una tarea una vez. Comprueba la siguiente ejecución.** Subes un video de referencia; Muse Spark y SAM 3.1 (API de Meta) proponen objetos, zonas y reglas; tú las apruebas; un motor determinista (sin IA) compara nuevas ejecuciones y devuelve PASS / FAIL / REVIEW con evidencia. Los modelos observan, el motor decide.

> Prototipo de investigación (Meta Global AI Developer Hackathon 2026). No apto para controles críticos ni de seguridad.

## Requisitos
Python 3.11+, Node 20+, `ffmpeg`/`ffprobe` en el PATH y una clave de la API de Meta.

## Arranque
```bash
# 1) Clave (solo backend; nunca se sube a git)
cp .env.example .env          # edita .env y pon MODEL_API_KEY=<tu clave>   (también vale META_API_KEY)

# 2) Backend  (http://localhost:8000)
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -e engine -e "backend[sam-masks]"
uvicorn app.main:app --app-dir backend --port 8000

# 3) Frontend (http://localhost:5173)
cd frontend && npm install && npm run dev
```
Abre http://localhost:5173. En «Enseñar» puedes usar los **videos de ejemplo sintéticos** incluidos (referencia + 4 ejecuciones: correcta, orden invertido, falta un objeto, mano tapando) o subir los tuyos (cámara fija, mesa a la vista, 2–4 objetos de colores distintos, MP4/MOV horizontal de 2–120 s).

## Pruebas
```bash
(cd engine && python -m pytest) && (cd backend && python -m pytest)   # sin red; usan respuestas grabadas
```

## Estructura
`engine/` motor determinista (sin red) · `backend/` API FastAPI, clientes Muse/SAM, trabajos · `frontend/` SPA React · `docs/` PRD, spec, contrato de API y hallazgos reales de la API de Meta (`docs/meta-findings.md`).

## Límites conocidos
Validado solo con videos sintéticos de bloques planos y llamadas reales a la API; falta video real (manos, luz, cámara móvil). La identidad entre clips se resuelve por la descripción del objeto (no hay correspondencia visual) y no se detecta cámara movida. Ver `docs/meta-findings.md`.
