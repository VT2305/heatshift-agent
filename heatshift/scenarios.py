from __future__ import annotations

import json
from pathlib import Path

from .tools.proposals import PENDING

BASE = Path(__file__).resolve().parent.parent
DATA = BASE / "data"


def _read(name: str):
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def _write(name: str, value):
    (DATA / name).write_text(json.dumps(value, indent=2), encoding="utf-8")


def reset_demo_state() -> dict:
    _write("workers.json", _read("baseline_workers.json"))
    _write("current_plan.json", _read("baseline_plan.json"))
    PENDING.clear()
    return {"status": "RESET", "plan_version": 1}


def set_worker_unavailable(worker_id: str = "W003") -> dict:
    workers = _read("workers.json")
    found = False
    for worker in workers:
        if worker["worker_id"] == worker_id:
            worker["status"] = "unavailable"
            found = True
    if not found:
        raise KeyError(worker_id)
    _write("workers.json", workers)
    return {"status": "SCENARIO_READY", "worker_id": worker_id, "availability": "unavailable"}


def set_no_feasible_roofing() -> dict:
    plan = _read("current_plan.json")
    workers = _read("workers.json")
    roof_item = next((i for i in plan["items"] if i["task_id"] == "T101"), None)
    target_ids = set(roof_item["worker_ids"] if roof_item else ["W001", "W002", "W003", "W004"])
    for worker in workers:
        if worker["worker_id"] in target_ids or "roofing" in worker.get("skills", []):
            worker["status"] = "unavailable"
    _write("workers.json", workers)
    return {"status": "SCENARIO_READY", "unavailable_roofing_workers": sorted(target_ids)}
