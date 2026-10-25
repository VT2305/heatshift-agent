from __future__ import annotations

from datetime import datetime
from uuid import uuid4
try:
    from ortools.sat.python import cp_model
except Exception:
    cp_model = None

from ..models import SiteState, HeatReading, WorkPlan, PlanItem, RequiredBreak
from ..timeutils import hm_to_min, min_to_hm
from .safety import max_rest_minutes
from .exposure import calculate_exposure

SLOT = 15
DAY_START = 8 * 60
DAY_END = 17 * 60 + 30


def _eligible_workers(state: SiteState, task) -> list[str]:
    result = []
    for w in state.workers:
        if w.status != "available":
            continue
        if task.environment.value == "outdoor" and not w.fit_for_outdoor_work:
            continue
        if not all(skill in w.skills for skill in task.required_skills):
            continue
        # Conservative MVP: acclimatising workers are not assigned to heavy outdoor tasks.
        if task.environment.value == "outdoor" and task.intensity.value == "heavy" and w.acclimatisation_status != "acclimatised":
            continue
        result.append(w.worker_id)
    return result


def _heat_at_minute(state: SiteState, minute: int, fallback: HeatReading) -> float:
    # Scenario points are aligned to 15-minute blocks. Choose nearest preceding point.
    if not state.heat_series:
        return fallback.wbgt_c
    vals = []
    for h in state.heat_series:
        mins = h.timestamp.hour * 60 + h.timestamp.minute
        if mins <= minute:
            vals.append((mins, h.wbgt_c))
    if vals:
        return max(vals, key=lambda x: x[0])[1]
    return fallback.wbgt_c


def _greedy_fallback(state: SiteState, heat: HeatReading, trigger: str) -> WorkPlan | None:
    """Conservative deterministic fallback used when CP-SAT cannot return a candidate."""
    current = {i.task_id: i for i in state.current_plan.items}
    tasks = list(state.tasks)

    # Preserve dependency correctness by scheduling fixed work first, then
    # high-priority tasks, while reserving time for direct successors.
    ordered = sorted(
        tasks,
        key=lambda t: (not t.fixed, -t.priority, hm_to_min(t.deadline), t.task_id),
    )

    occupied: list[tuple[int, int, list[str]]] = []
    scheduled_end: dict[str, int] = {}
    items: list[PlanItem] = []
    breaks: list[RequiredBreak] = []

    for task in ordered:
        eligible = _eligible_workers(state, task)
        if len(eligible) < task.workers_required:
            return None

        # Fixed tasks keep their existing workers when they remain valid.
        existing = current.get(task.task_id)
        if task.fixed and existing:
            if all(w in eligible for w in existing.worker_ids) and len(existing.worker_ids) >= task.workers_required:
                worker_ids = existing.worker_ids[:task.workers_required]
            else:
                worker_ids = eligible[:task.workers_required]
        else:
            worker_ids = eligible[:task.workers_required]

        if task.fixed and existing:
            candidates = [hm_to_min(existing.start)]
        else:
            decision_minute = heat.timestamp.hour * 60 + heat.timestamp.minute
            lo = max(DAY_START, decision_minute, hm_to_min(task.earliest_start))
            hi = min(DAY_END, hm_to_min(task.deadline)) - task.duration_minutes
            if hi < lo:
                return None
            candidates = list(range(lo, hi + 1, SLOT))
            cur_start = hm_to_min(existing.start) if existing else lo

            if task.environment.value == "outdoor" and task.intensity.value == "heavy":
                # Prefer cooler times but not so late that downstream work becomes impossible.
                candidates.sort(
                    key=lambda st: (
                        _heat_at_minute(state, st, heat),
                        abs(st - cur_start),
                        st,
                    )
                )
            else:
                candidates.sort(key=lambda st: (abs(st - cur_start), st))

        chosen = None
        for st in candidates:
            en = st + task.duration_minutes

            # If a direct successor exists, reserve its minimum duration before its deadline.
            downstream_latest = [
                hm_to_min(child.deadline) - child.duration_minutes
                for child in tasks
                if task.task_id in child.dependencies
            ]
            if downstream_latest and en > min(downstream_latest):
                continue

            # All already-scheduled predecessors must have finished.
            if any(dep in scheduled_end and st < scheduled_end[dep] for dep in task.dependencies):
                continue

            # No worker may be double-booked.
            if any(
                st < old_end and old_start < en and set(worker_ids) & set(old_workers)
                for old_start, old_end, old_workers in occupied
            ):
                continue

            chosen = (st, en)
            break

        if chosen is None:
            return None

        st, en = chosen
        occupied.append((st, en, worker_ids))
        scheduled_end[task.task_id] = en

        items.append(PlanItem(
            task_id=task.task_id,
            start=min_to_hm(st),
            end=min_to_hm(en),
            worker_ids=worker_ids,
            note="deterministic fallback candidate",
        ))

        wbgt = _heat_at_minute(state, st, heat)
        rest = max_rest_minutes(wbgt, task)
        if rest > 0 and task.duration_minutes >= 60:
            # Treat task.duration_minutes as the scheduled work window for this MVP.
            # Place the recovery block at the end of the first work-rest cycle.
            break_start = min(en - rest, st + (60 - rest))
            breaks.append(RequiredBreak(
                worker_ids=worker_ids,
                start=min_to_hm(break_start),
                minutes=rest,
                reason=f"Encoded heavy-work recovery requirement at WBGT {wbgt:.1f}°C",
            ))

    by_id = {i.task_id: i for i in items}
    for task in tasks:
        for dep in task.dependencies:
            if dep not in by_id or task.task_id not in by_id:
                return None
            if hm_to_min(by_id[task.task_id].start) < hm_to_min(by_id[dep].end):
                return None

    return WorkPlan(
        plan_id=f"PLAN-{uuid4().hex[:8].upper()}",
        version=state.current_plan.version + 1,
        generated_at=datetime.now().astimezone(),
        trigger=trigger,
        status="pending_supervisor_approval",
        items=items,
        required_breaks=breaks,
    )

def generate_safe_schedule(state: SiteState, heat: HeatReading, trigger: str) -> WorkPlan | None:
    if cp_model is None:
        return _greedy_fallback(state, heat, trigger)

    model = cp_model.CpModel()
    tasks = state.tasks
    current = {i.task_id: i for i in state.current_plan.items}

    start_vars = {}
    end_vars = {}
    intervals = {}
    chosen_workers = {}

    for task in tasks:
        eligible = _eligible_workers(state, task)
        if len(eligible) < task.workers_required:
            return None
        chosen_workers[task.task_id] = eligible[:task.workers_required]

        earliest = hm_to_min(task.earliest_start)
        deadline = hm_to_min(task.deadline)
        dur = task.duration_minutes

        decision_minute = heat.timestamp.hour * 60 + heat.timestamp.minute
        lo = max(DAY_START, decision_minute, earliest)
        hi = min(DAY_END, deadline) - dur
        if hi < lo:
            return None

        if task.fixed and task.task_id in current:
            fixed_start = hm_to_min(current[task.task_id].start)
            s = model.NewIntVar(fixed_start, fixed_start, f"s_{task.task_id}")
        else:
            s = model.NewIntVar(lo, hi, f"s_{task.task_id}")
            q = model.NewIntVar(lo // SLOT, hi // SLOT, f"q_{task.task_id}")
            model.Add(s == q * SLOT)

        e = model.NewIntVar(lo + dur, min(DAY_END, deadline), f"e_{task.task_id}")
        model.Add(e == s + dur)
        start_vars[task.task_id] = s
        end_vars[task.task_id] = e
        intervals[task.task_id] = model.NewIntervalVar(s, dur, e, f"iv_{task.task_id}")

    for task in tasks:
        for dep in task.dependencies:
            if dep in end_vars:
                model.Add(start_vars[task.task_id] >= end_vars[dep])

    for i, a in enumerate(tasks):
        for b in tasks[i+1:]:
            if set(chosen_workers[a.task_id]) & set(chosen_workers[b.task_id]):
                before = model.NewBoolVar(f"{a.task_id}_before_{b.task_id}")
                model.Add(end_vars[a.task_id] <= start_vars[b.task_id]).OnlyEnforceIf(before)
                model.Add(end_vars[b.task_id] <= start_vars[a.task_id]).OnlyEnforceIf(before.Not())

    terms = []
    for task in tasks:
        cur = current.get(task.task_id)
        if cur:
            cur_start = hm_to_min(cur.start)
            dev = model.NewIntVar(0, DAY_END, f"dev_{task.task_id}")
            model.AddAbsEquality(dev, start_vars[task.task_id] - cur_start)
            terms.append(3 * dev)
        if task.environment.value == "outdoor" and task.intensity.value == "heavy":
            for candidate in range(max(DAY_START, hm_to_min(task.earliest_start)),
                                   min(DAY_END, hm_to_min(task.deadline)) - task.duration_minutes + 1, SLOT):
                wbgt = _heat_at_minute(state, candidate, heat)
                penalty = int(max(0, wbgt - 31.0) * 40)
                b = model.NewBoolVar(f"start_{task.task_id}_{candidate}")
                model.Add(start_vars[task.task_id] == candidate).OnlyEnforceIf(b)
                model.Add(start_vars[task.task_id] != candidate).OnlyEnforceIf(b.Not())
                terms.append(penalty * b)

    model.Minimize(sum(terms))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 2.0
    solver.parameters.num_search_workers = 8
    status = solver.Solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return _greedy_fallback(state, heat, trigger)

    items = []
    breaks = []
    for task in tasks:
        st = solver.Value(start_vars[task.task_id])
        en = solver.Value(end_vars[task.task_id])
        worker_ids = chosen_workers[task.task_id]
        items.append(PlanItem(
            task_id=task.task_id,
            start=min_to_hm(st),
            end=min_to_hm(en),
            worker_ids=worker_ids,
        ))
        wbgt = _heat_at_minute(state, st, heat)
        rest = max_rest_minutes(wbgt, task)
        if rest:
            breaks.append(RequiredBreak(
                worker_ids=worker_ids,
                start=min_to_hm(min(en - rest, st + max(0, 60 - rest))),
                minutes=rest,
                reason=f"Encoded heavy-work recovery requirement at WBGT {wbgt:.1f}°C",
            ))

    return WorkPlan(
        plan_id=f"PLAN-{uuid4().hex[:8].upper()}",
        version=state.current_plan.version + 1,
        generated_at=datetime.now().astimezone(),
        trigger=trigger,
        status="pending_supervisor_approval",
        items=items,
        required_breaks=breaks,
    )
