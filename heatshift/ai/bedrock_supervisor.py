from __future__ import annotations

import os
from datetime import datetime
from uuid import uuid4

from strands import Agent
from strands.models import BedrockModel

from ..models import SupervisorDecision, DecisionCertificate
from ..store import audit
from ..prompt import SYSTEM_PROMPT
from .strands_tools import HeatShiftToolbox


BEDROCK_AGENT_PROMPT = SYSTEM_PROMPT + """

You are operating inside a bounded, auditable tool environment.

For every operational event:
1. Call get_site_state.
2. Call get_heat_state.
3. Call get_safety_constraints.
4. Call assess_current_plan.
5. If the plan is compliant, stop and explain that monitoring continues.
6. If non-compliant, call calculate_exposure.
7. Call generate_safe_schedule.
8. If no feasible candidate exists, stop and escalate without relaxing rules.
9. Call validate_schedule.
10. If validation fails, do not propose the plan.
11. If validation passes, call compare_plan_impact.
12. Call propose_plan_change.
13. Give one concise plain-English operational recommendation.

Do not call tools merely to repeat information.
Do not call propose_plan_change until validation passed and impact was calculated.
Never claim a simulated value is live.
Never describe the exposure proxy as a medical probability.
Never approve the proposal.
"""


class BedrockHeatShiftSupervisor:
    """Real Strands + Amazon Bedrock supervisor with deterministic tool authority."""

    def __init__(self):
        region = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION") or "ap-southeast-1"
        model_id = os.getenv("HEATSHIFT_BEDROCK_MODEL_ID", "global.anthropic.claude-sonnet-4-6")
        self.model = BedrockModel(
            model_id=model_id,
            region_name=region,
            temperature=0.1,
        )

    @staticmethod
    def _message_text(result) -> str:
        # Strands AgentResult string conversion is intentionally used as a compatibility
        # boundary across SDK versions. The structured decision itself comes from tools.
        text = str(result).strip()
        return text or "HeatShift completed the decision cycle."

    def run(self, event: str = "WBGT_RISE", use_simulated_heat: bool = True, scenario_index: int = 2) -> SupervisorDecision:
        decision_id = f"HS-AI-{uuid4().hex[:8].upper()}"
        toolbox = HeatShiftToolbox(
            event=event,
            scenario_index=scenario_index,
            use_simulated_heat=use_simulated_heat,
        )
        agent = Agent(
            name="HeatShift Supervisor",
            model=self.model,
            system_prompt=BEDROCK_AGENT_PROMPT,
            tools=[
                toolbox.get_site_state,
                toolbox.get_heat_state,
                toolbox.get_safety_constraints,
                toolbox.assess_current_plan,
                toolbox.calculate_exposure,
                toolbox.generate_safe_schedule,
                toolbox.validate_schedule,
                toolbox.compare_plan_impact,
                toolbox.propose_plan_change,
            ],
        )

        prompt = (
            f"Operational event: {event}. "
            "Run the HeatShift decision loop using the provided tools. "
            "Use tool evidence only; do not invent missing values."
        )
        result = agent(prompt)
        llm_message = self._message_text(result)

        heat = toolbox.heat
        data_quality = "SIMULATED"
        if heat is not None:
            data_quality = {
                "NEA_WBGT": "LIVE",
                "CACHED_NEA_WBGT": "CACHED",
                "SIMULATED": "SIMULATED",
            }[heat.source]

        rule_refs = []
        if toolbox.constraints:
            rule_refs = sorted({r["rule_id"] for r in toolbox.constraints})

        affected = []
        if toolbox.assessment:
            affected = toolbox.assessment.get("affected_tasks", [])

        if toolbox.assessment and toolbox.assessment.get("compliant"):
            decision = SupervisorDecision(
                decision_id=decision_id,
                status="MONITOR",
                trigger=event,
                affected_tasks=affected,
                rule_refs=rule_refs,
                data_quality=data_quality,
                requires_approval=False,
                supervisor_message=llm_message,
            )
            audit("BEDROCK_AGENT_DECISION", decision.model_dump(mode="json"))
            return decision

        if toolbox.candidate is None:
            status = "NO_FEASIBLE_PLAN" if toolbox.assessment is not None else "BLOCKED_MISSING_DATA"
            fallback = (
                "I could not produce a safe, valid plan. I did not relax any hard safety rule. "
                "Supervisor action is required."
            )
            decision = SupervisorDecision(
                decision_id=decision_id,
                status=status,
                trigger=event,
                affected_tasks=affected,
                rule_refs=rule_refs,
                data_quality=data_quality,
                requires_approval=True,
                supervisor_message=llm_message if llm_message else fallback,
            )
            audit("BEDROCK_AGENT_DECISION", decision.model_dump(mode="json"))
            return decision

        if toolbox.validation is None or not toolbox.validation.valid or not toolbox.proposed:
            decision = SupervisorDecision(
                decision_id=decision_id,
                status="BLOCKED_MISSING_DATA",
                trigger=event,
                affected_tasks=affected,
                rule_refs=rule_refs,
                data_quality=data_quality,
                requires_approval=True,
                supervisor_message=(
                    "The AI decision cycle did not complete every mandatory safety gate, "
                    "so HeatShift refused to publish a proposal."
                ),
            )
            audit("BEDROCK_AGENT_DECISION", decision.model_dump(mode="json"))
            return decision

        impact = toolbox.impact
        toolbox.candidate.metrics = toolbox.candidate.metrics.model_copy(update=impact.model_dump())
        toolbox.candidate.explanation = llm_message

        certificate = DecisionCertificate(
            decision_id=decision_id,
            trigger=event,
            affected_tasks=affected,
            rule_refs=rule_refs,
            validation=toolbox.validation,
            impact=impact,
            data_provenance=heat.source if heat else "UNKNOWN",
            ruleset_version="MOM_HEAT_RULES_2026-08",
            human_approval="PENDING",
            tool_timeline=toolbox.timeline,
        )

        decision = SupervisorDecision(
            decision_id=decision_id,
            status="CHANGE_RECOMMENDED",
            trigger=event,
            affected_tasks=affected,
            rule_refs=rule_refs,
            impact=impact,
            data_quality=data_quality,
            requires_approval=True,
            supervisor_message=llm_message,
            proposed_plan=toolbox.candidate,
            certificate=certificate,
        )
        audit("BEDROCK_AGENT_DECISION", decision.model_dump(mode="json"))
        return decision
