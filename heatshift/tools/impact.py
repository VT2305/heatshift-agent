from __future__ import annotations
from ..models import SiteState, WorkPlan, HeatReading, ImpactMetrics
from ..timeutils import hm_to_min
from .exposure import calculate_exposure
from .safety import max_rest_minutes


def _wbgt_at(state: SiteState, hm: str, fallback: HeatReading) -> float:
    target = hm_to_min(hm)
    vals = []
    for r in state.heat_series:
        minute = r.timestamp.hour * 60 + r.timestamp.minute
        if minute <= target:
            vals.append((minute, r.wbgt_c))
    return max(vals, key=lambda x: x[0])[1] if vals else fallback.wbgt_c


def compare_plan_impact(state: SiteState, new_plan: WorkPlan, heat: HeatReading, compliance: bool) -> ImpactMetrics:
    tasks = {t.task_id: t for t in state.tasks}
    old = {i.task_id: i for i in state.current_plan.items}
    new = {i.task_id: i for i in new_plan.items}

    moved = 0
    reassign = 0
    delay = 0
    overtime = 0
    exposure_before = 0.0
    exposure_after = 0.0

    for tid, ni in new.items():
        task = tasks[tid]
        oi = old.get(tid)

        if oi:
            if oi.start != ni.start:
                moved += 1
            delay += max(0, hm_to_min(ni.end) - hm_to_min(oi.end))
            reassign += len(set(ni.worker_ids) ^ set(oi.worker_ids))
            old_wbgt = _wbgt_at(state, oi.start, heat)
        else:
            old_wbgt = heat.wbgt_c

        new_wbgt = _wbgt_at(state, ni.start, heat)
        overtime += max(0, hm_to_min(ni.end) - 17 * 60)

        old_rest = 0  # current plan is the baseline being compared
        new_rest = max_rest_minutes(new_wbgt, task)

        exposure_before += calculate_exposure(task, old_wbgt, task.duration_minutes, old_rest)
        exposure_after += calculate_exposure(task, new_wbgt, task.duration_minutes, new_rest)

    reduction = 0.0
    if exposure_before > 0:
        reduction = max(0.0, (exposure_before - exposure_after) / exposure_before * 100.0)

    return ImpactMetrics(
        delay_minutes=int(delay),
        tasks_moved=moved,
        worker_reassignments=reassign,
        overtime_minutes=int(overtime),
        exposure_proxy_before=round(exposure_before, 1),
        exposure_proxy_after=round(exposure_after, 1),
        exposure_proxy_reduction_pct=round(reduction, 1),
        compliance=compliance,
    )
