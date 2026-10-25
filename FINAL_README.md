# HeatShift — Final Competition Build

## One-line product
HeatShift is a climate-adaptive site-supervisor agent that turns WBGT, workforce state, task constraints and deterministic heat-safety rules into a validated work-plan proposal, then stops at a human approval boundary.

## What the judge sees
Open `http://localhost:8080`.

Recommended demo:
1. `Reset Demo`
2. `01 · Heat spike`
3. Show agent tool timeline + Decision Certificate
4. `Approve validated plan`
5. `02 · Worker unavailable`
6. Show second replan
7. If asked about edge cases: `03 · No feasible plan`

## Architecture
- Dashboard: judge-facing operations UI
- FastAPI: application/API layer
- Amazon Bedrock + Strands: real AI supervisor mode
- Deterministic rules: safety authority
- OR-Tools CP-SAT: schedule authority
- Deterministic validator: mandatory gate
- Decision Certificate: impact + provenance + rule references
- Human supervisor: approval authority
- Audit log: decision trace and plan versions

## Install

```powershell
python -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
.venv\Scripts\Activate.ps1
pip install -e ".[aws,dev]"
pytest -q
uvicorn heatshift.app:app --reload --port 8080
```

Then open:
`http://localhost:8080`

## Reliable demo mode
Use `Resilient local agent`. It does not require AWS or internet.

## Real Bedrock mode
Use `Amazon Bedrock agent` after AWS credentials/model access are configured.

Optional environment variables:

```powershell
$env:AWS_REGION="ap-southeast-1"
$env:HEATSHIFT_BEDROCK_MODEL_ID="<model-enabled-in-your-hackathon-account>"
```

## Live Singapore WBGT
The live adapter uses data.gov.sg's documented weather sub-API:

`https://api-open.data.gov.sg/v2/real-time/api/weather?api=wbgt`

Optional higher-rate-limit key:

```powershell
$env:DATA_GOV_SG_API_KEY="<your-key>"
```

HeatShift never calls simulated data "live". Live failures fall back to cache when available; otherwise the competition scenario stays labelled SIMULATED.

## Prototype boundary
Decision-support MVP only. Not a medical device. Does not diagnose heat illness. Encoded rules must be verified against the official source and organisation SOP before real deployment.
