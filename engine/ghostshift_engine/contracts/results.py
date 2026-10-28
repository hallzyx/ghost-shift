"""Resultados del motor: eventos, evidencias y veredictos (spec §4, §6)."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Tri(str, Enum):
    TRUE = "TRUE"
    FALSE = "FALSE"
    UNKNOWN = "UNKNOWN"


class Verdict(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    REVIEW = "REVIEW"
    SKIPPED = "SKIPPED"


@dataclass(frozen=True)
class Event:
    kind: str  # "place" | "remove"
    obj: str
    zone: str | None
    k: int
    t_lo: int
    t_hi: int
    frame_key: int
    timing_uncertain: bool = False
    identity_suspect: bool = False


@dataclass(frozen=True)
class Evidence:
    kind: str  # "event" | "state" | "absence_probe"
    obj: str
    t_ms: int
    frame: int | None = None
    detail: str = ""


@dataclass
class Outcome:
    value: Tri
    reason: str
    evidence: list[Evidence] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)


@dataclass
class RuleResult:
    rule_id: str
    text_es: str
    verdict: Verdict
    reason: str
    evidence: list[Evidence] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)


@dataclass
class RunReport:
    procedure_id: str
    version: int
    content_hash: str
    verdict: Verdict
    rules: list[RuleResult]
    blocking_issues: list[str]
    events: list[Event]
    params_hash: str
    engine_version: str
    camera_status: str = "ALIGNED"
