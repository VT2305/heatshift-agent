from __future__ import annotations
from ..models import Task

INTENSITY = {"light": 1.0, "moderate": 1.5, "heavy": 2.2}
ENV = {"indoor": 0.3, "shaded": 0.7, "outdoor": 1.0}

def calculate_exposure(task: Task, wbgt_c: float, duration_minutes: int, recovery_minutes: int = 0) -> float:
    # Operational exposure proxy only. Not a medical-risk probability.
    heat_factor = max(0.5, (wbgt_c - 25.0) / 7.0)
    gross = duration_minutes * INTENSITY[task.intensity.value] * ENV[task.environment.value] * heat_factor
    recovery_credit = recovery_minutes * 1.3
    return round(max(0.0, gross - recovery_credit), 2)
