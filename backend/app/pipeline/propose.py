"""Propone zonas y reglas a partir de las pistas de SAM y la propuesta de Muse (sin red).

Las zonas salen de dónde terminan los objetos (SAM); Muse aporta nombres y contraste. Lo que Muse
dice y SAM no respalda se marca como hipótesis y llega desactivado (TECH_SPEC §3.1, EP-02).
"""
from __future__ import annotations

from statistics import median

from ghostshift_engine import EngineParams, Procedure, TrackSet, compile_procedure
from ghostshift_engine.contracts.tracks import FrameObs
from ghostshift_engine.events import detect_events
from ghostshift_engine.features import build_timelines, resolve_identities
from ghostshift_engine.rules import ON, stack_relation

WORKSPACE = {"id": "ws", "role": "workspace", "label": "Área de trabajo",
             "polygon": [[0.02, 0.05], [0.98, 0.05], [0.98, 0.97], [0.02, 0.97]]}
EXPAND = 1.7  # la zona es la caja de reposo ampliada
ORDER_TOLERANCE_S = 1.5


def _resolved_obs(tracks: TrackSet, ids: list[str]) -> dict[str, dict]:
    """Una observación por objeto y fotograma con la misma resolución de identidad que el motor."""
    chosen, _ = resolve_identities(tracks, ids, EngineParams())
    return {oid: {f: o for f, o in per.items() if isinstance(o, FrameObs)} for oid, per in chosen.items()}


def _stack_pairs(rests: dict[str, tuple]) -> list[tuple[str, str]]:
    """(arriba, base) para cada objeto que al final está directamente encima de otro (geometría del motor)."""
    p = EngineParams()
    pairs = []
    for top, tb in sorted(rests.items()):
        below = [(stack_relation(tb, bb, p)[1]["rise"], base) for base, bb in sorted(rests.items())
                 if base != top and stack_relation(tb, bb, p)[0] == ON]
        if below:
            pairs.append((top, min(below)[1]))  # la base más cercana: la de menor elevación
    return pairs


def _iou(a, b) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    i = ix * iy
    u = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - i
    return i / u if u else 0.0


def _rest_box(obs: dict, fps: float) -> tuple | None:
    frames = sorted(obs)
    last = frames[-1]
    win = [f for f in frames if f >= last - int(fps)]
    return tuple(median(obs[f].bbox[i] for f in win) for i in range(4))


def _zone_rect(box) -> tuple:
    cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    hw, hh = max((box[2] - box[0]) / 2 * EXPAND, 0.05), max((box[3] - box[1]) / 2 * EXPAND, 0.05)
    return (max(0.02, cx - hw), max(0.05, cy - hh), min(0.98, cx + hw), min(0.97, cy + hh))


def _positional_labels(rects: list[tuple]) -> list[str]:
    n = len(rects)
    if n == 1:
        return ["Zona de destino"]
    cx = [(r[0] + r[2]) / 2 for r in rects]
    cy = [(r[1] + r[3]) / 2 for r in rects]
    if max(cx) - min(cx) >= max(cy) - min(cy):
        names = {2: ["izquierda", "derecha"], 3: ["izquierda", "centro", "derecha"]}.get(n)
        order = sorted(range(n), key=lambda i: cx[i])
    else:
        names = {2: ["superior", "inferior"], 3: ["superior", "centro", "inferior"]}.get(n)
        order = sorted(range(n), key=lambda i: cy[i])
    out = [""] * n
    for rank, i in enumerate(order):
        out[i] = f"Zona {names[rank]}" if names else f"Zona {rank + 1}"
    return out


def propose_draft(tracks: TrackSet, objects: list[dict], muse: dict | None = None) -> dict:
    """`objects`: [{id, label_es, sam_prompt}]. Devuelve el borrador del contrato (objects/zones/rules/timeline/uncertainties)."""
    muse = muse or {}
    fps, t = tracks.clip.analysis_fps, tracks.clip.frame_t_ms
    n = len(t)
    uncertainties = list(muse.get("uncertainties", []))
    obj_defs, rests, seen = [], {}, {}
    resolved = _resolved_obs(tracks, [o["id"] for o in objects])
    for o in objects:
        obs = resolved[o["id"]]
        label = o["label_es"]
        obj_defs.append({"id": o["id"], "description": label, "sam_prompt": o["sam_prompt"],
                         "confirmed_by_user": True,
                         "ref_max_score": max((x.score for x in obs.values()), default=None)})
        if not obs:
            uncertainties.append(f"No se pudo seguir «{label}» en el video. Revisa su descripción en inglés (¿\"{o['sam_prompt']}\"?) o que se vea bien.")
            continue
        seen[o["id"]] = obs
        if max(obs) < n - 1 - 2 * int(fps):
            uncertainties.append(f"«{label}» deja de verse antes del final del video; no se propone una zona final para él.")
            continue
        rests[o["id"]] = _rest_box(obs, fps)

    # zonas: una por posición final; se fusionan las que se solapan
    groups: list[dict] = []
    for oid, box in sorted(rests.items(), key=lambda kv: (kv[1][0] + kv[1][2])):
        rect = _zone_rect(box)
        for g in groups:
            if _iou(g["rect"], rect) > 0.25:
                g["rect"] = (min(g["rect"][0], rect[0]), min(g["rect"][1], rect[1]),
                             max(g["rect"][2], rect[2]), max(g["rect"][3], rect[3]))
                g["objs"].append(oid)
                break
        else:
            groups.append({"rect": rect, "objs": [oid]})
    labels = _positional_labels([g["rect"] for g in groups]) if groups else []
    zones = [dict(WORKSPACE)]
    obj_zone: dict[str, str] = {}
    for i, (g, lab) in enumerate(zip(groups, labels), 1):
        zid = f"z{i}"
        x0, y0, x1, y1 = g["rect"]
        for mz in muse.get("zones", []):  # nombre de Muse si su caja contiene el centro de la zona
            b = mz.get("bbox", [])
            if len(b) == 4 and b[0] <= (x0 + x1) / 2 <= b[2] and b[1] <= (y0 + y1) / 2 <= b[3] and mz.get("label_es"):
                lab = mz["label_es"]
                break
        zones.append({"id": zid, "role": "target", "label": lab,
                      "polygon": [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]})
        for oid in g["objs"]:
            obj_zone[oid] = zid
    zlabel = {z["id"]: z["label"] for z in zones}
    desc = {o["id"]: o["label_es"] for o in objects}

    rules = [{"id": f"R{i}", "type": "in_zone_at", "enabled": True, "origin": "proposed", "object": oid,
              "zone": zid, "at": "end", "text_es": f"«{desc[oid]}» debe quedar en {zlabel[zid].lower()} al terminar."}
             for i, (oid, zid) in enumerate(sorted(obj_zone.items()), 1)]
    # apilado: si al final un objeto está directamente encima de otro, la posición en zona no basta
    # (unas cintas tiradas dentro de la zona también la cumplen); se propone la relación vertical.
    stack_pairs = _stack_pairs(rests)
    below = dict(stack_pairs)  # arriba -> base

    def same_tower(a: str, b: str) -> bool:
        def chain(x):
            seen = []
            while x in below and x not in seen:
                seen.append(x)
                x = below[x]
            return set(seen) | {x}
        return b in chain(a) or a in chain(b)

    for top, base in stack_pairs:
        rules.append({"id": f"R{len(rules) + 1}", "type": "stacked_on", "enabled": True, "origin": "proposed",
                      "object": top, "base": base,
                      "text_es": f"«{desc[top]}» debe quedar apilado directamente sobre «{desc[base]}» al terminar."})

    timeline: list[dict] = []
    first_place: dict[str, int] = {}
    if rules:
        proc = compile_procedure(Procedure.model_validate({
            "procedure_id": "tmp", "approved_by_user": True,
            "objects": [{k: d[k] for k in ("id", "description", "ref_max_score")} for d in obj_defs],
            "zones": zones, "rules": [{k: v for k, v in r.items() if k != "text_es"} for r in rules]}))
        params = EngineParams()
        for oid, tl in build_timelines(tracks, proc, params).items():
            for e in detect_events(tl, proc, tracks, params).events:
                if e.kind == "place" and e.zone is not None:
                    timeline.append({"kind": "place", "object": oid, "zone": e.zone, "t_ms": e.t_hi,
                                     "confidence": "sam_confirmed"})
                    first_place.setdefault(oid, e.t_hi)
    muse_t = {}
    for ev in muse.get("events", []):
        muse_t.setdefault(ev["object"], int(ev["t_seconds"] * 1000))
    for oid, tm in muse_t.items():
        if oid not in first_place and oid in desc:
            uncertainties.append(f"Muse Spark cree que «{desc[oid]}» se coloca hacia {tm / 1000:.1f} s, pero SAM no lo respalda; no se crea regla.")
            timeline.append({"kind": "place", "object": oid, "zone": obj_zone.get(oid), "t_ms": tm, "confidence": "muse_only"})
    timeline.sort(key=lambda e: e["t_ms"])

    ordered = sorted(first_place, key=first_place.get)
    for a, b in zip(ordered, ordered[1:]):
        if same_tower(a, b):
            # el orden de colocación ya está implícito en el apilado (no se puede poner algo sobre una base
            # que aún no está) y con manos reales los instantes de colocación son poco precisos
            uncertainties.append(f"No se propone «{desc[a]}» antes que «{desc[b]}»: el orden ya lo exige el apilado.")
            continue
        ra, rb = muse_t.get(a), muse_t.get(b)
        disagree = ra is not None and rb is not None and ra > rb + ORDER_TOLERANCE_S * 1000
        rule = {"id": f"R{len(rules) + 1}", "type": "before", "enabled": not disagree,
                "origin": "hypothesis" if disagree else "proposed", "first": f"place:{a}", "second": f"place:{b}",
                "text_es": f"«{desc[a]}» debe colocarse antes que «{desc[b]}»."}
        if disagree:
            uncertainties.append(f"Muse Spark y SAM no coinciden en el orden de «{desc[a]}» y «{desc[b]}»; la regla llega desactivada.")
        rules.append(rule)
    if not rules:
        uncertainties.append("No se detectó ningún objeto que quede en reposo. Comprueba que el video muestre la tarea completa con cámara fija.")
    return {"objects": obj_defs, "zones": zones, "rules": rules, "timeline": timeline, "uncertainties": uncertainties}
