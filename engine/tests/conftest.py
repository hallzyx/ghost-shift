import pytest

from ghostshift_engine import Procedure, compile_procedure
from ghostshift_engine.synth import SynthObject

LEFT, RIGHT, MID = (0.20, 0.50), (0.80, 0.50), (0.50, 0.50)


def procedure(rules=None, objects=("A", "B"), ref_score=0.9):
    zones = [
        {"id": "workspace", "role": "workspace", "polygon": [(0.05, 0.1), (0.95, 0.1), (0.95, 0.95), (0.05, 0.95)]},
        {"id": "left", "polygon": [(0.10, 0.40), (0.30, 0.40), (0.30, 0.60), (0.10, 0.60)]},
        {"id": "right", "polygon": [(0.70, 0.40), (0.90, 0.40), (0.90, 0.60), (0.70, 0.60)]},
    ]
    rules = rules or [
        {"id": "R1", "type": "in_zone_at", "object": "A", "zone": "left", "at": "end"},
        {"id": "R2", "type": "in_zone_at", "object": "B", "zone": "right", "at": "end"},
        {"id": "R3", "type": "before", "first": "place:A", "second": "place:B"},
    ]
    return compile_procedure(Procedure(
        procedure_id="kit", approved_by_user=True, zones=zones, rules=rules,
        objects=[{"id": o, "ref_max_score": ref_score} for o in objects]))


def place(obj_id, start_pos, end_pos, t_move, dur=800, **kw):
    """Objeto en reposo en start_pos, se mueve a end_pos entre t_move y t_move+dur."""
    return SynthObject(obj_id, [(0, *start_pos), (t_move, *start_pos), (t_move + dur, *end_pos)], **kw)


@pytest.fixture
def proc():
    return procedure()
