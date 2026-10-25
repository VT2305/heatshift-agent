from heatshift.agent import HeatShiftSupervisor

def test_heat_spike_triggers_valid_proposal():
    d = HeatShiftSupervisor().run(event="WBGT_RISE", use_simulated_heat=True, scenario_index=2)
    assert d.status in {"CHANGE_RECOMMENDED", "NO_FEASIBLE_PLAN"}
    if d.status == "CHANGE_RECOMMENDED":
        assert d.certificate is not None
        assert d.certificate.validation.valid
        assert d.proposed_plan.status == "pending_supervisor_approval"
        tools = [x["tool"] for x in d.certificate.tool_timeline]
        assert tools[:4] == [
            "get_site_state",
            "get_heat_state",
            "get_safety_constraints",
            "assess_current_plan",
        ]
        assert "generate_safe_schedule" in tools
        assert "validate_schedule" in tools
        assert "compare_plan_impact" in tools
        assert "propose_plan_change" in tools

def test_cool_weather_monitors():
    d = HeatShiftSupervisor().run(event="CHECK", use_simulated_heat=True, scenario_index=0)
    assert d.status == "MONITOR"
    assert d.requires_approval is False
