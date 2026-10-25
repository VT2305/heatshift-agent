from __future__ import annotations

from typing import Any
from strands import tool

from ..store import load_site_state
from ..tools.weather import get_heat_state as _get_heat_state
from ..tools.safety import get_safety_constraints as _get_safety_constraints
from ..tools.assess import assess_current_plan as _assess_current_plan
from ..tools.exposure import calculate_exposure as _calculate_exposure
from ..tools.scheduler import generate_safe_schedule as _generate_safe_schedule
from ..tools.validator import validate_schedule as _validate_schedule
from ..tools.impact import compare_plan_impact as _compare_plan_impact
from ..tools.proposals import propose_plan_change as _propose_plan_change


class HeatShiftToolbox:
    """
    Stateful tool boundary for the Bedrock/Strands supervisor.

    The model chooses which tool to call, but tools enforce ordering and
    deterministic safety gates. The model never gets authority to approve
    a plan or modify the encoded rules.
    """

    def __init__(self, *, event: str, scenario_index: int, use_simulated_heat: bool):
        self.event = event
        self.scenario_index = scenario_index
        self.use_simulated_heat = use_simulated_heat

        self.state = None
        self.heat = None
        self.constraints: list[dict[str, Any]] | None = None
        self.assessment = None
        self.candidate = None
        self.validation = None
        self.impact = None
        self.proposed = False

        self.timeline: list[dict[str, Any]] = []
        self.tool_calls = 0
        self.max_tool_calls = 12

    def _record(self, tool_name: str, result: str, details: dict[str, Any] | None = None):
        self.tool_calls += 1
        if self.tool_calls > self.max_tool_calls:
            raise RuntimeError("Bounded-agent guardrail: maximum tool calls exceeded")
        self.timeline.append({
            "tool": tool_name,
            "result": result,
            "details": details or {},
        })

    def _need(self, value, message: str):
        if value is None:
            raise RuntimeError(message)
        return value

    @tool
    def get_site_state(self) -> dict:
        """Load the current site state.

        Returns a compact view of workers, tasks, task windows, dependencies,
        availability, skills, current assignments, and current plan version.
        """
        self.state = load_site_state()
        result = {
            "site_id": self.state.site_id,
            "plan_version": self.state.current_plan.version,
            "workers": [
                {
                    "worker_id": w.worker_id,
                    "team": w.team,
                    "skills": w.skills,
                    "acclimatisation_status": w.acclimatisation_status,
                    "status": w.status,
                }
                for w in self.state.workers
            ],
            "tasks": [
                {
                    "task_id": t.task_id,
                    "name": t.name,
                    "environment": t.environment.value,
                    "intensity": t.intensity.value,
                    "duration_minutes": t.duration_minutes,
                    "workers_required": t.workers_required,
                    "required_skills": t.required_skills,
                    "earliest_start": t.earliest_start,
                    "deadline": t.deadline,
                    "fixed": t.fixed,
                    "dependencies": t.dependencies,
                }
                for t in self.state.tasks
            ],
            "current_plan": self.state.current_plan.model_dump(mode="json"),
        }
        self._record("get_site_state", "OK", {
            "workers": len(self.state.workers),
            "tasks": len(self.state.tasks),
            "plan_version": self.state.current_plan.version,
        })
        return result

    @tool
    def get_heat_state(self) -> dict:
        """Load the authoritative heat input for this decision cycle.

        The returned source explicitly indicates whether the reading is live,
        cached, or simulated. Never infer a missing heat value.
        """
        self.heat = _get_heat_state(
            use_simulated=self.use_simulated_heat,
            scenario_index=self.scenario_index,
        )
        result = self.heat.model_dump(mode="json")
        self._record("get_heat_state", "OK", {
            "wbgt_c": self.heat.wbgt_c,
            "source": self.heat.source,
            "band": self.heat.heat_band,
        })
        return result

    @tool
    def get_safety_constraints(self) -> dict:
        """Retrieve deterministic encoded safety constraints for site tasks.

        This tool is the only authority for the rules used in this prototype.
        The model must not invent or relax any rule.
        """
        state = self._need(self.state, "Call get_site_state before get_safety_constraints.")
        heat = self._need(self.heat, "Call get_heat_state before get_safety_constraints.")
        rows = []
        seen = set()
        for task in state.tasks:
            for c in _get_safety_constraints(heat.wbgt_c, task):
                key = (task.task_id, c.rule_id)
                if key in seen:
                    continue
                seen.add(key)
                rows.append({
                    "task_id": task.task_id,
                    "task_name": task.name,
                    **c.model_dump(mode="json"),
                })
        self.constraints = rows
        self._record("get_safety_constraints", "OK", {
            "rule_refs": sorted({r["rule_id"] for r in rows})
        })
        return {
            "wbgt_c": heat.wbgt_c,
            "ruleset_version": rows[0]["source_version"] if rows else "unknown",
            "constraints": rows,
        }

    @tool
    def assess_current_plan(self) -> dict:
        """Check whether the current plan conflicts with encoded heat constraints.

        Returns compliance status and the affected tasks. This is deterministic.
        """
        state = self._need(self.state, "Call get_site_state before assess_current_plan.")
        heat = self._need(self.heat, "Call get_heat_state before assess_current_plan.")
        self._need(self.constraints, "Call get_safety_constraints before assess_current_plan.")
        self.assessment = _assess_current_plan(state, heat)
        self._record(
            "assess_current_plan",
            "COMPLIANT" if self.assessment["compliant"] else "CONFLICT",
            self.assessment,
        )
        return self.assessment

    @tool
    def calculate_exposure(self) -> dict:
        """Calculate an operational heat-exposure proxy for affected tasks.

        This proxy is not a medical probability and must never be described as
        risk of heat stroke, illness probability, or diagnosis.
        """
        state = self._need(self.state, "Call get_site_state before calculate_exposure.")
        heat = self._need(self.heat, "Call get_heat_state before calculate_exposure.")
        assessment = self._need(self.assessment, "Call assess_current_plan before calculate_exposure.")
        affected = set(assessment["affected_tasks"])
        rows = []
        total = 0.0
        for task in state.tasks:
            if affected and task.task_id not in affected:
                continue
            val = _calculate_exposure(task, heat.wbgt_c, task.duration_minutes, 0)
            total += val
            rows.append({"task_id": task.task_id, "exposure_proxy": val})
        self._record("calculate_exposure", "OK", {"aggregate_proxy": round(total, 2)})
        return {
            "aggregate_exposure_proxy": round(total, 2),
            "affected_task_proxies": rows,
            "medical_probability": False,
        }

    @tool
    def generate_safe_schedule(self) -> dict:
        """Generate a lower-disruption schedule satisfying hard constraints.

        Uses OR-Tools CP-SAT when available. Returns NO_FEASIBLE_PLAN when no
        valid candidate can be generated without weakening hard constraints.
        """
        state = self._need(self.state, "Call get_site_state before generate_safe_schedule.")
        heat = self._need(self.heat, "Call get_heat_state before generate_safe_schedule.")
        assessment = self._need(self.assessment, "Call assess_current_plan before generate_safe_schedule.")
        if assessment["compliant"]:
            raise RuntimeError("Current plan is compliant; do not generate an unnecessary replacement.")
        self.candidate = _generate_safe_schedule(state, heat, self.event)
        if self.candidate is None:
            self._record("generate_safe_schedule", "NO_FEASIBLE_PLAN", {})
            return {"status": "NO_FEASIBLE_PLAN"}
        self._record("generate_safe_schedule", "OK", {"plan_id": self.candidate.plan_id})
        return {
            "status": "CANDIDATE_READY",
            "plan": self.candidate.model_dump(mode="json"),
        }

    @tool
    def validate_schedule(self) -> dict:
        """Validate the candidate schedule against hard operational constraints.

        This tool is a mandatory gate. A plan may not be proposed unless this
        returns valid=true.
        """
        state = self._need(self.state, "Call get_site_state before validate_schedule.")
        heat = self._need(self.heat, "Call get_heat_state before validate_schedule.")
        candidate = self._need(self.candidate, "Call generate_safe_schedule before validate_schedule.")
        self.validation = _validate_schedule(state, candidate, heat)
        self._record(
            "validate_schedule",
            "PASS" if self.validation.valid else "FAIL",
            {
                "checks": self.validation.checks,
                "issues": [i.model_dump() for i in self.validation.issues],
            },
        )
        return self.validation.model_dump(mode="json")

    @tool
    def compare_plan_impact(self) -> dict:
        """Compare the validated candidate with the current active plan.

        Reports schedule delay, tasks moved, reassignments, overtime,
        compliance, and the non-medical exposure-proxy change.
        """
        state = self._need(self.state, "Call get_site_state before compare_plan_impact.")
        heat = self._need(self.heat, "Call get_heat_state before compare_plan_impact.")
        candidate = self._need(self.candidate, "Call generate_safe_schedule before compare_plan_impact.")
        validation = self._need(self.validation, "Call validate_schedule before compare_plan_impact.")
        if not validation.valid:
            raise RuntimeError("Cannot compare/publish an invalid candidate.")
        self.impact = _compare_plan_impact(state, candidate, heat, validation.valid)
        self._record("compare_plan_impact", "OK", self.impact.model_dump())
        return self.impact.model_dump()

    @tool
    def propose_plan_change(self) -> dict:
        """Create a human-approval proposal for the validated candidate.

        This DOES NOT approve or publish the plan. The AI is forbidden from
        approving its own recommendation.
        """
        candidate = self._need(self.candidate, "Call generate_safe_schedule before propose_plan_change.")
        validation = self._need(self.validation, "Call validate_schedule before propose_plan_change.")
        self._need(self.impact, "Call compare_plan_impact before propose_plan_change.")
        if not validation.valid:
            raise RuntimeError("Cannot propose an invalid schedule.")
        if self.proposed:
            return {"status": "ALREADY_PENDING_APPROVAL", "plan_id": candidate.plan_id}
        _propose_plan_change(candidate)
        self.proposed = True
        self._record("propose_plan_change", "PENDING_APPROVAL", {"plan_id": candidate.plan_id})
        return {
            "status": "PENDING_SUPERVISOR_APPROVAL",
            "plan_id": candidate.plan_id,
            "ai_can_approve": False,
        }
