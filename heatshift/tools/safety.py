from __future__ import annotations

import json
from pathlib import Path
from ..models import SafetyConstraint, Task

RULES = Path(__file__).resolve().parents[2] / "rules" / "mom_heat_rules.v2026-08.json"


def _load_rules() -> dict:
    return json.loads(RULES.read_text())


def get_safety_constraints(wbgt_c: float, task: Task) -> list[SafetyConstraint]:
    raw = _load_rules()
    version = raw["version"]
    out: list[SafetyConstraint] = []

    hydration = raw["hydration"]
    out.append(SafetyConstraint(
        rule_id=hydration["rule_id"],
        description=hydration["description"],
        hydration_ml_per_hour=hydration["ml_per_hour"],
        source_version=version,
    ))

    if task.environment.value == "outdoor" and task.intensity.value == "heavy":
        for rule in raw["heavy_outdoor_rest"]:
            if wbgt_c >= rule["min_wbgt_c"]:
                out.append(SafetyConstraint(
                    rule_id=rule["rule_id"],
                    description=rule["description"],
                    rest_minutes_per_hour=rule["rest_minutes_per_hour"],
                    source_version=version,
                ))
                break

    if task.environment.value == "outdoor":
        out.append(SafetyConstraint(
            rule_id=raw["acclimatisation"]["rule_id"],
            description=raw["acclimatisation"]["description"],
            source_version=version,
        ))
    return out


def max_rest_minutes(wbgt_c: float, task: Task) -> int:
    cs = get_safety_constraints(wbgt_c, task)
    return max((c.rest_minutes_per_hour for c in cs), default=0)
