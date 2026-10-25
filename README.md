# HeatShift Supervisor Agent

HeatShift is a decision-support agent for construction-site heat operations in Singapore.

It converts **site state + WBGT + versioned safety rules + task constraints** into a validated work-plan proposal. The LLM is never the source of truth for safety thresholds and cannot approve its own schedule.

## Architecture

`PERCEIVE -> ASSESS -> PLAN -> VERIFY -> EXPLAIN -> HUMAN APPROVAL -> AUDIT -> ADAPT`

Tools:
1. `get_site_state`
2. `get_heat_state`
3. `get_safety_constraints`
4. `assess_current_plan`
5. `calculate_exposure`
6. `generate_safe_schedule`
7. `validate_schedule`
8. `compare_plan_impact`
9. `propose_plan_change`

## Safety properties

- Versioned deterministic safety rules
- No medical diagnosis
- No invented WBGT or worker data
- No publication without validation
- No publication without human approval
- Bounded orchestration loop
- Every run produces an audit trail
- Live-data fallback is visibly labelled `cached` or `simulated`

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
uvicorn heatshift.app:app --reload --port 8080
```

Open:

- `GET http://localhost:8080/ping`
- `GET http://localhost:8080/api/state`
- `POST http://localhost:8080/api/scenario/heat-spike`
- `POST http://localhost:8080/invocations`

Example:

```bash
curl -X POST http://localhost:8080/invocations \
  -H "Content-Type: application/json" \
  -d '{"event":"WBGT_RISE","use_simulated_heat":true}'
```

Approve the pending proposal:

```bash
curl -X POST http://localhost:8080/api/proposals/approve \
  -H "Content-Type: application/json" \
  -d '{"plan_id":"PLAN-...","supervisor":"demo-supervisor"}'
```

## Tests

```bash
pytest -q
```

## AWS AgentCore

A deployable entrypoint is included as `agentcore_entrypoint.py`.

Install AWS extras:

```bash
pip install -e ".[aws]"
```

Then use the current AgentCore CLI flow configured for your hackathon AWS account. The local FastAPI app remains the reliable fallback demo path.

## Important prototype note

HeatShift is a hackathon decision-support MVP. It is not a medical device, does not diagnose heat illness, and does not replace statutory workplace-safety obligations or supervisor judgment.

The rules file in `rules/mom_heat_rules.v2026-08.json` is intentionally versioned. Before a real deployment, have the exact encoded rules verified against the official MOM source and your organisation's approved SOP.
