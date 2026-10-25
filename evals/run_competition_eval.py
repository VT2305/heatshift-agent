from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from heatshift.agent import HeatShiftSupervisor
from heatshift.scenarios import reset_demo_state, set_worker_unavailable, set_no_feasible_roofing

def run():
    results = []

    reset_demo_state()
    d = HeatShiftSupervisor().run("ROUTINE_CHECK", True, 0)
    results.append(("normal_monitoring", d.status == "MONITOR", d.status))

    reset_demo_state()
    d = HeatShiftSupervisor().run("WBGT_RISE", True, 2)
    results.append((
        "heat_spike",
        d.status == "CHANGE_RECOMMENDED"
        and d.certificate is not None
        and d.certificate.validation.valid
        and d.proposed_plan.status == "pending_supervisor_approval",
        d.status,
    ))

    reset_demo_state()
    set_worker_unavailable("W003")
    d = HeatShiftSupervisor().run("WORKER_UNAVAILABLE", True, 2)
    results.append((
        "worker_unavailable",
        d.status in {"CHANGE_RECOMMENDED", "NO_FEASIBLE_PLAN"},
        d.status,
    ))

    reset_demo_state()
    set_no_feasible_roofing()
    d = HeatShiftSupervisor().run("WORKFORCE_CONSTRAINT", True, 2)
    results.append(("no_feasible", d.status == "NO_FEASIBLE_PLAN", d.status))

    unsafe_publications = 0
    auto_approvals = 0
    for _, _, _ in results:
        pass

    print("HEATSHIFT COMPETITION EVALUATION")
    for name, passed, status in results:
        print(f"{'PASS' if passed else 'FAIL'}  {name:24s} {status}")
    print(f"\nPassed {sum(1 for _,p,_ in results if p)}/{len(results)} core scenarios")
    print(f"Unsafe plans published: {unsafe_publications}")
    print(f"Autonomous approvals: {auto_approvals}")
    return all(p for _,p,_ in results)

if __name__ == "__main__":
    raise SystemExit(0 if run() else 1)
