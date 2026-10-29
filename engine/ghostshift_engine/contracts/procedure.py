"""Procedimiento aprobado y su compilación (spec §2)."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from ..geometry import polygon_area, polygon_is_simple, rasterize_polygon

RuleType = Literal["present_in_zone", "in_zone_at", "before", "stacked_on"]


class ObjectDef(BaseModel):
    id: str
    description: str = ""  # nombre para el usuario (español)
    sam_prompt: str = ""  # frase corta en inglés con que SAM busca el objeto
    confirmed_by_user: bool = True
    ref_max_score: float | None = None  # score de SAM en la referencia (habilita FAIL por ausencia)
    indistinguishable_from: list[str] = Field(default_factory=list)


class Zone(BaseModel):
    id: str
    role: Literal["workspace", "target", "staging"] = "target"
    label: str = ""
    polygon: list[tuple[float, float]]


class Rule(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    type: RuleType
    enabled: bool = True
    origin: Literal["proposed", "user", "hypothesis"] = "proposed"
    text_es: str = ""
    object: str | None = None
    zone: str | None = None
    at: Literal["end", "during"] | None = None
    from_: str | None = Field(default=None, alias="from")
    to: str | None = None
    first: str | None = None
    second: str | None = None
    base: str | None = None  # stacked_on: «object» debe quedar directamente encima de «base» al terminar
    occurrence: Literal["both_agree", "first", "definitive"] = "both_agree"


class Procedure(BaseModel):
    schema_version: Literal["ghostshift.procedure/2"] = "ghostshift.procedure/2"
    procedure_id: str
    version: int = 1
    parent_version: int | None = None
    approved_by_user: bool = False
    objects: list[ObjectDef]
    zones: list[Zone]
    rules: list[Rule]

    def content_hash(self) -> str:
        data = self.model_dump(mode="json", by_alias=True)
        blob = json.dumps(data, sort_keys=True).encode()
        return "sha256:" + hashlib.sha256(blob).hexdigest()


class ProcedureError(ValueError):
    """Error accionable para Rule Studio."""


@dataclass(frozen=True)
class CompiledProcedure:
    procedure: Procedure
    content_hash: str
    workspace_id: str
    grids: dict[str, np.ndarray]  # zona -> máscara booleana rasterizada
    target_zones: tuple[str, ...]

    @property
    def active_rules(self) -> list[Rule]:
        return [r for r in self.procedure.rules if r.enabled]


def parse_event_ref(ref: str) -> tuple[str, str | None]:
    """'place:A' o 'place:A@left' -> ('A', None|'left')."""
    kind, _, rest = ref.partition(":")
    if kind != "place" or not rest:
        raise ProcedureError(f"Referencia de evento no soportada: {ref!r}")
    obj, _, zone = rest.partition("@")
    return obj, (zone or None)


def _has_cycle(edges: list[tuple[str, str]]) -> bool:
    graph: dict[str, set[str]] = {}
    for a, b in edges:
        graph.setdefault(a, set()).add(b)
        graph.setdefault(b, set())
    color: dict[str, int] = {}

    def visit(n: str) -> bool:
        color[n] = 1
        for m in graph[n]:
            if color.get(m, 0) == 1 or (color.get(m, 0) == 0 and visit(m)):
                return True
        color[n] = 2
        return False

    return any(color.get(n, 0) == 0 and visit(n) for n in graph)


def compile_procedure(proc: Procedure) -> CompiledProcedure:
    if not proc.approved_by_user:
        raise ProcedureError("El procedimiento no está aprobado por el usuario.")
    objs = {o.id for o in proc.objects}
    zones = {z.id: z for z in proc.zones}
    workspaces = [z.id for z in proc.zones if z.role == "workspace"]
    if len(workspaces) != 1:
        raise ProcedureError("Debe haber exactamente una zona con rol 'workspace'.")
    for z in proc.zones:
        if polygon_area(z.polygon) < 0.002 or not polygon_is_simple(z.polygon):
            raise ProcedureError(f"La zona {z.id!r} tiene un polígono inválido o demasiado pequeño.")
    active = [r for r in proc.rules if r.enabled]
    if not active:
        raise ProcedureError("No hay ninguna regla habilitada.")
    order_edges: list[tuple[str, str]] = []
    stack_edges: list[tuple[str, str]] = []
    for r in active:
        if r.type == "stacked_on":
            if r.object not in objs or r.base not in objs:
                raise ProcedureError(f"Regla {r.id}: 'stacked_on' requiere un objeto y una base existentes.")
            if r.object == r.base:
                raise ProcedureError(f"Regla {r.id}: un objeto no puede estar apilado sobre sí mismo.")
            if any(a == r.object for a, _ in stack_edges):
                raise ProcedureError(f"Regla {r.id}: «{r.object}» ya tiene otra base; solo puede apoyarse sobre una.")
            stack_edges.append((r.object, r.base))
        elif r.type in ("present_in_zone", "in_zone_at"):
            if r.object not in objs:
                raise ProcedureError(f"Regla {r.id}: objeto inexistente {r.object!r}.")
            if r.type == "in_zone_at" and r.at is None:
                raise ProcedureError(f"Regla {r.id}: in_zone_at requiere 'at'.")
            if r.zone is not None and r.zone not in zones:
                raise ProcedureError(f"Regla {r.id}: zona inexistente {r.zone!r}.")
            if r.type == "in_zone_at" and r.zone is None:
                raise ProcedureError(f"Regla {r.id}: in_zone_at requiere 'zone'.")
        else:
            if not r.first or not r.second:
                raise ProcedureError(f"Regla {r.id}: 'before' requiere first y second.")
            if r.first == r.second:
                raise ProcedureError(f"Regla {r.id}: first y second no pueden ser iguales.")
            for ref in (r.first, r.second):
                o, z = parse_event_ref(ref)
                if o not in objs or (z is not None and z not in zones):
                    raise ProcedureError(f"Regla {r.id}: referencia inexistente en {ref!r}.")
            order_edges.append((r.first, r.second))
    if _has_cycle(order_edges):
        raise ProcedureError("Las reglas de orden forman un ciclo; no existe un orden posible.")
    if _has_cycle(stack_edges):
        raise ProcedureError("Las reglas de apilado forman un ciclo; no existe una torre posible.")
    grids = {zid: rasterize_polygon(z.polygon) for zid, z in zones.items()}
    targets = tuple(z.id for z in proc.zones if z.role == "target")
    return CompiledProcedure(proc, proc.content_hash(), workspaces[0], grids, targets)
