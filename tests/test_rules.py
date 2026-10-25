from heatshift.tools.safety import get_safety_constraints
from heatshift.models import Task

def heavy_task():
    return Task(
        task_id="T",
        name="Heavy work",
        zone="z",
        environment="outdoor",
        intensity="heavy",
        duration_minutes=60,
        workers_required=1,
        required_skills=[],
        earliest_start="08:00",
        deadline="17:00",
    )

def test_rest_10_at_32_4():
    rules = get_safety_constraints(32.4, heavy_task())
    assert max(r.rest_minutes_per_hour for r in rules) == 10

def test_rest_15_at_33():
    rules = get_safety_constraints(33.0, heavy_task())
    assert max(r.rest_minutes_per_hour for r in rules) == 15

def test_no_heavy_rest_under_32():
    rules = get_safety_constraints(31.9, heavy_task())
    assert max(r.rest_minutes_per_hour for r in rules) == 0
