from __future__ import annotations

from ..models import SiteState, WorkPlan, HeatReading, ValidationResult, ValidationIssue
from ..timeutils import hm_to_min
from .safety import max_rest_minutes

def _wbgt_at_start(state: SiteState, start: str, fallback: HeatReading) -> float:
    target = hm_to_min(start)
    candidates = []
    for reading in state.heat_series:
        minute = reading.timestamp.hour * 60 + reading.timestamp.minute
        if minute <= target:
            candidates.append((minute, reading.wbgt_c))
    if candidates:
        return max(candidates, key=lambda x: x[0])[1]
    return fallback.wbgt_c


def validate_schedule(state: SiteState, plan: WorkPlan, heat: HeatReading) -> ValidationResult:
    issues: list[ValidationIssue] = []
    checks = 0
    tasks = {t.task_id: t for t in state.tasks}
    workers = {w.worker_id: w for w in state.workers}

    # item field + bounds checks
    for item in plan.items:
        checks += 1
        task = tasks.get(item.task_id)
        if not task:
            issues.append(ValidationIssue(code="UNKNOWN_TASK", message=item.task_id))
            continue
        if hm_to_min(item.start) < hm_to_min(task.earliest_start) or hm_to_min(item.end) > hm_to_min(task.deadline):
            issues.append(ValidationIssue(code="TASK_WINDOW", message=f"{task.task_id} outside allowed window"))
        if len(item.worker_ids) < task.workers_required:
            issues.append(ValidationIssue(code="UNDERSTAFFED", message=f"{task.task_id} requires {task.workers_required} workers"))
        for wid in item.worker_ids:
            w = workers.get(wid)
            if not w or w.status != "available":
                issues.append(ValidationIssue(code="WORKER_UNAVAILABLE", message=f"{wid} unavailable"))
                continue
            if not all(skill in w.skills for skill in task.required_skills):
                issues.append(ValidationIssue(code="SKILL_MISMATCH", message=f"{wid} lacks required skill for {task.task_id}"))

    # worker double booking
    for i, a in enumerate(plan.items):
        for b in plan.items[i+1:]:
            checks += 1
            overlap = hm_to_min(a.start) < hm_to_min(b.end) and hm_to_min(b.start) < hm_to_min(a.end)
            if overlap and set(a.worker_ids) & set(b.worker_ids):
                issues.append(ValidationIssue(
                    code="DOUBLE_BOOKING",
                    message=f"{a.task_id} overlaps {b.task_id} for shared workers",
                ))

    # dependencies
    by_task = {i.task_id: i for i in plan.items}
    for task in state.tasks:
        for dep in task.dependencies:
            checks += 1
            if dep in by_task and task.task_id in by_task:
                if hm_to_min(by_task[task.task_id].start) < hm_to_min(by_task[dep].end):
                    issues.append(ValidationIssue(
                        code="DEPENDENCY",
                        message=f"{task.task_id} starts before dependency {dep} ends",
                    ))

    # fixed tasks
    current = {i.task_id: i for i in state.current_plan.items}
    for task in state.tasks:
        if task.fixed and task.task_id in current and task.task_id in by_task:
            checks += 1
            if by_task[task.task_id].start != current[task.task_id].start:
                issues.append(ValidationIssue(code="FIXED_TASK_MOVED", message=task.task_id))

    # explicit recovery break presence for heavy outdoor work under current heat.
    for item in plan.items:
        task = tasks[item.task_id]
        task_wbgt = _wbgt_at_start(state, item.start, heat)
        rest = max_rest_minutes(task_wbgt, task)
        if rest:
            checks += 1
            relevant_breaks = [
                b for b in plan.required_breaks
                if set(item.worker_ids).issubset(set(b.worker_ids))
                and hm_to_min(item.start) <= hm_to_min(b.start)
                and hm_to_min(b.start) + b.minutes <= hm_to_min(item.end)
            ]
            supplied = sum(b.minutes for b in relevant_breaks)
            if supplied < rest:
                issues.append(ValidationIssue(
                    code="REST_REQUIREMENT",
                    message=f"{task.task_id} needs at least {rest} recovery minutes/hour under encoded rules",
                ))

    return ValidationResult(valid=not any(i.severity == "error" for i in issues), checks=checks, issues=issues)
