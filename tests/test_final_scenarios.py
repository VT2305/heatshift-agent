from heatshift.scenarios import reset_demo_state, set_worker_unavailable, set_no_feasible_roofing
from heatshift.agent import HeatShiftSupervisor

def test_worker_unavailable_forces_reassessment():
    reset_demo_state()
    set_worker_unavailable("W003")
    d = HeatShiftSupervisor().run("WORKER_UNAVAILABLE", True, 2)
    assert "T101" in d.affected_tasks
    assert d.status in {"CHANGE_RECOMMENDED", "NO_FEASIBLE_PLAN"}

def test_no_feasible_scenario_refuses_to_relax_constraints():
    reset_demo_state()
    set_no_feasible_roofing()
    d = HeatShiftSupervisor().run("WORKFORCE_CONSTRAINT", True, 2)
    assert d.status == "NO_FEASIBLE_PLAN"

def test_heat_spike_proposal_remains_human_pending():
    reset_demo_state()
    d = HeatShiftSupervisor().run("WBGT_RISE", True, 2)
    assert d.status == "CHANGE_RECOMMENDED"
    assert d.proposed_plan is not None
    assert d.proposed_plan.status == "pending_supervisor_approval"
    assert d.certificate.human_approval == "PENDING"
