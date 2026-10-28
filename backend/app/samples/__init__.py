"""Vídeos de ejemplo SINTÉTICOS (bloques de colores) para probar la app sin grabar."""
from pathlib import Path

DIR = Path(__file__).parent

SAMPLES = [
    {"id": "reference", "kind": "reference", "title_es": "Referencia: azul a la izquierda, luego amarillo a la derecha",
     "description_es": "Video sintético de ejemplo: un bloque azul entra por la izquierda y después uno amarillo por la derecha.",
     "expected": None},
    {"id": "run_ok", "kind": "run", "title_es": "Ejecución correcta",
     "description_es": "Mismo orden y mismas posiciones que la referencia, con tiempos distintos.", "expected": "PASS"},
    {"id": "run_wrong_order", "kind": "run", "title_es": "Orden invertido",
     "description_es": "El bloque amarillo se coloca antes que el azul.", "expected": "FAIL"},
    {"id": "run_missing_b", "kind": "run", "title_es": "Falta el bloque amarillo",
     "description_es": "El bloque amarillo nunca aparece.", "expected": "FAIL"},
    {"id": "run_hand_at_end", "kind": "run", "title_es": "Mano tapa un bloque al final",
     "description_es": "Una mano tapa el bloque azul hasta el final del video.", "expected": "REVIEW"},
]
BY_ID = {s["id"]: s for s in SAMPLES}


def path(sample_id: str) -> Path:
    return DIR / f"{sample_id}.mp4"
