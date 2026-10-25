from __future__ import annotations

from ..models import SiteState, HeatReading
from .safety import max_rest_minutes


def assess_current_plan(state: SiteState, heat: HeatReading) -> dict:
    tasks = {t.task_id: t for t in state.tasks}
    workers = {w.worker_id: w for w in state.workers}
    affected: list[str] = []
    reasons: list[dict] = []

    for item in state.current_plan.items:
        task = tasks[item.task_id]

        unavailable = [
            wid for wid in item.worker_ids
            if wid not in workers or workers[wid].status != "available"
        ]
        if unavailable:
            if task.task_id not in affected:
                affected.append(task.task_id)
            reasons.append({
                "type": "WORKER_UNAVAILABLE",
                "task_id": task.task_id,
                "worker_ids": unavailable,
            })

        rest = max_rest_minutes(heat.wbgt_c, task)
        if rest <= 0:
            continue

        supplied = 0
        for b in state.current_plan.required_breaks:
            if set(item.worker_ids).issubset(set(b.worker_ids)):
                supplied += b.minutes

        if supplied < rest:
            if task.task_id not in affected:
                affected.append(task.task_id)
            reasons.append({
                "type": "HEAT_RECOVERY_CONFLICT",
                "task_id": task.task_id,
                "required_rest_minutes": rest,
                "scheduled_rest_minutes": supplied,
            })

    return {
        "compliant": not affected,
        "affected_tasks": affected,
        "reasons": reasons,
    }
