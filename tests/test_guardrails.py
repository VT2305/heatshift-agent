from heatshift.agent import HeatShiftSupervisor
from heatshift.tools.proposals import approve_plan

def test_agent_does_not_auto_approve():
    d = HeatShiftSupervisor().run(event="WBGT_RISE", use_simulated_heat=True, scenario_index=2)
    if d.proposed_plan:
        assert d.proposed_plan.status == "pending_supervisor_approval"

def test_certificate_shows_provenance():
    d = HeatShiftSupervisor().run(event="WBGT_RISE", use_simulated_heat=True, scenario_index=2)
    if d.certificate:
        assert d.certificate.data_provenance == "SIMULATED"
        assert d.certificate.ruleset_version == "MOM_HEAT_RULES_2026-08"
