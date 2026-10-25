from __future__ import annotations
from ..models import WorkPlan
from ..store import save_current_plan, audit

PENDING: dict[str, WorkPlan] = {}

def propose_plan_change(plan: WorkPlan) -> None:
    if plan.status != "pending_supervisor_approval":
        raise ValueError("Only pending plans may be proposed")
    PENDING[plan.plan_id] = plan
    audit("PLAN_PROPOSED", {"plan_id": plan.plan_id, "version": plan.version})

def approve_plan(plan_id: str, supervisor: str) -> WorkPlan:
    if plan_id not in PENDING:
        raise KeyError("Unknown pending plan")
    plan = PENDING.pop(plan_id)
    approved = plan.model_copy(update={"status": "approved"})
    save_current_plan(approved)
    audit("PLAN_APPROVED", {"plan_id": plan_id, "supervisor": supervisor})
    return approved

def reject_plan(plan_id: str, supervisor: str, reason: str) -> WorkPlan:
    if plan_id not in PENDING:
        raise KeyError("Unknown pending plan")
    plan = PENDING.pop(plan_id)
    rejected = plan.model_copy(update={"status": "rejected"})
    audit("PLAN_REJECTED", {"plan_id": plan_id, "supervisor": supervisor, "reason": reason})
    return rejected
