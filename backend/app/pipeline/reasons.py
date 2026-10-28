"""Códigos de razón del motor -> explicación en español."""
REASONS_ES = {
    "IN_ZONE": "El objeto está dentro de la zona esperada.",
    "OUT_OF_ZONE": "El objeto se ve fuera de la zona esperada.",
    "PRESENT": "El objeto estuvo presente en la zona el tiempo necesario.",
    "ORDER_OK": "Las colocaciones ocurrieron en el orden esperado.",
    "ORDER_VIOLATED": "Las colocaciones ocurrieron en orden inverso al esperado.",
    "ORDER_OVERLAP": "Las dos colocaciones están demasiado juntas en el tiempo para decidir el orden.",
    "ORDER_NOT_OBSERVED": "No se observaron las colocaciones necesarias para decidir el orden.",
    "ORDER_AMBIGUOUS_REPLACEMENT": "Hubo recolocaciones y el orden depende de cuál se considere: necesita revisión humana.",
    "EVENT_NOT_OCCURRED": "El segundo objeto no llegó a colocarse en el video.",
    "FIRST_EVENT_MISSING_BEFORE_SECOND": "El primer objeto no se colocó antes que el segundo.",
    "OBJECT_NOT_FOUND": "El objeto no aparece en todo el video, mientras que los demás sí se ven.",
    "OBJECT_REMOVED": "El objeto salió de la escena antes del final.",
    "NOT_VISIBLE_AT_END": "No se ve el objeto al terminar (puede estar tapado): no se puede asegurar su posición.",
    "BORDERLINE_POSITION": "El objeto está justo en el borde de la zona: no se puede asegurar que esté dentro.",
    "ABSENCE_UNCONFIRMED": "No se detecta el objeto, pero no se puede confirmar que realmente falte.",
    "ANCHOR_EVENT_MISSING": "No se observó el evento que marca el inicio del intervalo.",
    "DURING_NOT_VERIFIABLE": "No hay visibilidad continua suficiente para comprobar el intervalo.",
    "ZONE_EXITED": "El objeto salió de la zona durante el intervalo.",
    "STAYED_IN_ZONE": "El objeto permaneció en la zona durante el intervalo.",
    "IDENTITY_SUSPECT": "El objeto parece haber cambiado de identidad (salto imposible): necesita revisión humana.",
    "IDENTITY_UNCONFIRMED": "La identidad del objeto no está confirmada.",
    "INSUFFICIENT_OBSERVATION": "No se observó nada utilizable en el video.",
    "CAMERA_INCOMPATIBLE": "La cámara es incompatible con la del video de referencia.",
    "CAMERA_MOVED": "La cámara parece haberse movido.",
    "DISABLED": "Regla desactivada.",
    "INTERNAL_NO_EVIDENCE": "No hay evidencia suficiente para sostener un fallo.",
}


def reason_es(code: str) -> str:
    return REASONS_ES.get(code, code)
