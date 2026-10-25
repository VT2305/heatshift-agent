from __future__ import annotations

import os
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .agent import HeatShiftSupervisor
from .store import load_site_state, read_audit
from .tools.proposals import approve_plan, reject_plan, PENDING
from .tools.weather import get_live_heat_state, get_cached_heat_state
from .scenarios import reset_demo_state, set_worker_unavailable, set_no_feasible_roofing

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"

app = FastAPI(
    title="HeatShift Supervisor Agent",
    version="1.0.0-final",
    description="Climate-adaptive workforce orchestration — competition build",
)

class Invocation(BaseModel):
    event: str = "WBGT_RISE"
    use_simulated_heat: bool = True
    scenario_index: int = 2

class Approval(BaseModel):
    plan_id: str
    supervisor: str

class Rejection(Approval):
    reason: str = "Supervisor rejected proposed plan"

class DemoRun(BaseModel):
    scenario: str = "heat_spike"
    mode: str = "local"

@app.get("/", include_in_schema=False)
def dashboard():
    return FileResponse(FRONTEND_DIR / "index.html")

@app.get("/ping")
def ping():
    return {"status": "healthy", "build": "competition-final"}

@app.get("/api/state")
def state():
    return load_site_state()

@app.get("/api/audit")
def audit_log(limit: int = 100):
    return read_audit(limit)

@app.get("/api/proposals")
def proposals():
    return [p.model_dump(mode="json") for p in PENDING.values()]

@app.get("/api/agent/status")
def agent_status():
    has_region = bool(os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION"))
    has_static_creds = bool(os.getenv("AWS_ACCESS_KEY_ID") and os.getenv("AWS_SECRET_ACCESS_KEY"))
    has_bearer = bool(os.getenv("AWS_BEARER_TOKEN_BEDROCK"))
    return {
        "local_agent": "ready",
        "bedrock_agent": "credentials_detected" if (has_static_creds or has_bearer) else "needs_aws_credentials",
        "aws_region_configured": has_region,
        "model_id": os.getenv("HEATSHIFT_BEDROCK_MODEL_ID", "global.anthropic.claude-sonnet-4-6"),
        "safety_authority": "deterministic_versioned_rules",
        "approval_authority": "human_only",
    }

@app.get("/api/heat/live")
def live_heat():
    try:
        return get_live_heat_state()
    except Exception as e:
        cached = get_cached_heat_state()
        if cached is not None:
            return cached
        raise HTTPException(status_code=502, detail=f"Live WBGT unavailable and no cache exists: {e}")

@app.get("/api/evidence")
def evidence():
    return {
        "architecture": {
            "ai_supervisor": "Amazon Bedrock + Strands (optional live mode)",
            "safety_authority": "Versioned deterministic rules",
            "scheduling_authority": "OR-Tools CP-SAT",
            "validation_gate": "Deterministic validator",
            "approval_authority": "Human supervisor only",
        },
        "guardrails": [
            "AI cannot approve its own plan",
            "AI cannot modify encoded safety rules",
            "Validator must pass before proposal",
            "Live/cached/simulated provenance is explicit",
            "Exposure score is labelled as a non-medical proxy",
            "Bounded tool loop",
        ],
        "demo_scenarios": [
            "Heat spike",
            "Worker unavailable",
            "No feasible safe plan",
            "Normal monitoring",
        ],
    }

@app.post("/api/demo/reset")
def reset_demo():
    return reset_demo_state()

@app.post("/api/demo/run")
def run_demo(payload: DemoRun):
    scenario = payload.scenario.lower().strip()
    mode = payload.mode.lower().strip()

    if scenario == "heat_spike":
        event, idx = "WBGT_RISE", 2
    elif scenario == "worker_unavailable":
        set_worker_unavailable("W003")
        event, idx = "WORKER_UNAVAILABLE", 2
    elif scenario == "no_feasible":
        set_no_feasible_roofing()
        event, idx = "WORKFORCE_CONSTRAINT", 2
    elif scenario == "monitor":
        event, idx = "ROUTINE_CHECK", 0
    else:
        raise HTTPException(status_code=400, detail="Unknown scenario")

    if mode == "bedrock":
        try:
            from .ai.bedrock_supervisor import BedrockHeatShiftSupervisor
            return BedrockHeatShiftSupervisor().run(
                event=event,
                use_simulated_heat=True,
                scenario_index=idx,
            )
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Bedrock mode failed: {e}")

    return HeatShiftSupervisor().run(
        event=event,
        use_simulated_heat=True,
        scenario_index=idx,
    )

@app.post("/api/agent/bedrock")
def invoke_bedrock(payload: Invocation):
    try:
        from .ai.bedrock_supervisor import BedrockHeatShiftSupervisor
    except ImportError:
        raise HTTPException(
            status_code=503,
            detail='Bedrock/Strands extras are not installed. Run: pip install -e ".[aws]"',
        )
    try:
        return BedrockHeatShiftSupervisor().run(
            event=payload.event,
            use_simulated_heat=payload.use_simulated_heat,
            scenario_index=payload.scenario_index,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Bedrock agent invocation failed: {e}")

@app.post("/invocations")
def invoke(payload: Invocation):
    return HeatShiftSupervisor().run(
        event=payload.event,
        use_simulated_heat=payload.use_simulated_heat,
        scenario_index=payload.scenario_index,
    )

@app.post("/api/scenario/heat-spike")
def heat_spike():
    return HeatShiftSupervisor().run(event="WBGT_RISE", use_simulated_heat=True, scenario_index=2)

@app.post("/api/proposals/approve")
def approve(payload: Approval):
    try:
        return approve_plan(payload.plan_id, payload.supervisor)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))

@app.post("/api/proposals/reject")
def reject(payload: Rejection):
    try:
        return reject_plan(payload.plan_id, payload.supervisor, payload.reason)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
