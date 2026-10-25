from __future__ import annotations

from datetime import datetime
from uuid import uuid4
import json

from .models import (
    SupervisorDecision,
    DecisionCertificate,
)
from .store import audit
from .tools.site_state import get_site_state
from .tools.weather import get_heat_state
from .tools.safety import get_safety_constraints
from .tools.assess import assess_current_plan
from .tools.scheduler import generate_safe_schedule
from .tools.validator import validate_schedule
from .tools.impact import compare_plan_impact
from .tools.proposals import propose_plan_change


class HeatShiftSupervisor:
    MAX_TOOL_CALLS = 12
    MAX_REPLAN_ATTEMPTS = 2

    def __init__(self):
        self.timeline: list[dict] = []
        self.tool_calls = 0

    def _record(self, tool: str, result: str, details: dict | None = None):
        self.tool_calls += 1
        if self.tool_calls > self.MAX_TOOL_CALLS:
            raise RuntimeError("Bounded-agent guardrail: maximum tool calls exceeded")
        self.timeline.append({
            "time": datetime.now().astimezone().isoformat(timespec="seconds"),
            "tool": tool,
            "result": result,
            "details": details or {},
        })

    def run(self, event: str = "WBGT_RISE", use_simulated_heat: bool = True, scenario_index: int = 2) -> SupervisorDecision:
        self.timeline = []
        self.tool_calls = 0
        decision_id = f"HS-{uuid4().hex[:8].upper()}"

        state = get_site_state()
        self._record("get_site_state", "OK", {
            "site_id": state.site_id,
            "workers": len(state.workers),
            "tasks": len(state.tasks),
            "plan_version": state.current_plan.version,
        })

        heat = get_heat_state(use_simulated=use_simulated_heat, scenario_index=scenario_index)
        self._record("get_heat_state", "OK", {
            "wbgt_c": heat.wbgt_c,
            "source": heat.source,
            "band": heat.heat_band,
        })

        # Tool 3: retrieve constraints for active tasks.
        rule_refs: set[str] = set()
        for task in state.tasks:
            constraints = get_safety_constraints(heat.wbgt_c, task)
            rule_refs.update(c.rule_id for c in constraints)
        self._record("get_safety_constraints", "OK", {"rule_refs": sorted(rule_refs)})

        assessment = assess_current_plan(state, heat)
        self._record(
            "assess_current_plan",
            "COMPLIANT" if assessment["compliant"] else "CONFLICT",
            assessment,
        )

        data_quality = {
            "NEA_WBGT": "LIVE",
            "CACHED_NEA_WBGT": "CACHED",
            "SIMULATED": "SIMULATED",
        }[heat.source]

        if assessment["compliant"]:
            msg = (
                f"Current plan remains compliant at WBGT {heat.wbgt_c:.1f}°C under the encoded rules. "
                "No schedule change is recommended. I will keep monitoring for a heat, worker, task or zone change."
            )
            decision = SupervisorDecision(
                decision_id=decision_id,
                status="MONITOR",
                trigger=event,
                affected_tasks=[],
                rule_refs=sorted(rule_refs),
                data_quality=data_quality,
                requires_approval=False,
                supervisor_message=msg,
            )
            audit("AGENT_DECISION", decision.model_dump(mode="json"))
            return decision

        # PLAN -> VERIFY. Two attempts maximum.
        plan = None
        validation = None
        for attempt in range(1, self.MAX_REPLAN_ATTEMPTS + 1):
            plan = generate_safe_schedule(state, heat, event)
            if plan is None:
                self._record("generate_safe_schedule", "NO_FEASIBLE_PLAN", {"attempt": attempt})
                continue
            self._record("generate_safe_schedule", "OK", {
                "attempt": attempt,
                "plan_id": plan.plan_id,
            })
            validation = validate_schedule(state, plan, heat)
            self._record("validate_schedule", "PASS" if validation.valid else "FAIL", {
                "checks": validation.checks,
                "issues": [i.model_dump() for i in validation.issues],
            })
            if validation.valid:
                break
            plan = None

        if plan is None or validation is None or not validation.valid:
            msg = (
                "I could not produce a safe, valid schedule within the bounded replanning attempts. "
                "I have not relaxed any hard safety rule. Supervisor action is required: adjust the deadline, "
                "qualified manpower, task scope, or site constraints."
            )
            decision = SupervisorDecision(
                decision_id=decision_id,
                status="NO_FEASIBLE_PLAN",
                trigger=event,
                affected_tasks=assessment["affected_tasks"],
                rule_refs=sorted(rule_refs),
                data_quality=data_quality,
                requires_approval=True,
                supervisor_message=msg,
            )
            audit("AGENT_DECISION", decision.model_dump(mode="json"))
            return decision

        impact = compare_plan_impact(state, plan, heat, validation.valid)
        self._record("compare_plan_impact", "OK", impact.model_dump())

        plan.metrics = plan.metrics.model_copy(update=impact.model_dump())
        affected_names = [t.name for t in state.tasks if t.task_id in assessment["affected_tasks"]]
        task_phrase = ", ".join(affected_names) or "the affected outdoor work"

        msg = (
            f"Heat conditions changed to WBGT {heat.wbgt_c:.1f}°C and {task_phrase} conflicts with the encoded "
            "heavy-work recovery requirement. I generated and validated a lower-disruption replacement plan. "
            f"It moves {impact.tasks_moved} task(s), adds {impact.delay_minutes} minute(s) of schedule delay, "
            f"and reduces the calculated heat-exposure proxy by {impact.exposure_proxy_reduction_pct:.1f}%. "
            "No hard safety rule was relaxed. Approve this plan?"
        )
        plan.explanation = msg

        propose_plan_change(plan)
        self._record("propose_plan_change", "PENDING_APPROVAL", {"plan_id": plan.plan_id})

        certificate = DecisionCertificate(
            decision_id=decision_id,
            trigger=event,
            affected_tasks=assessment["affected_tasks"],
            rule_refs=sorted(rule_refs),
            validation=validation,
            impact=impact,
            data_provenance=heat.source,
            ruleset_version="MOM_HEAT_RULES_2026-08",
            human_approval="PENDING",
            tool_timeline=self.timeline,
        )

        decision = SupervisorDecision(
            decision_id=decision_id,
            status="CHANGE_RECOMMENDED",
            trigger=event,
            affected_tasks=assessment["affected_tasks"],
            rule_refs=sorted(rule_refs),
            impact=impact,
            data_quality=data_quality,
            requires_approval=True,
            supervisor_message=msg,
            proposed_plan=plan,
            certificate=certificate,
        )
        audit("AGENT_DECISION", decision.model_dump(mode="json"))
        return decision
