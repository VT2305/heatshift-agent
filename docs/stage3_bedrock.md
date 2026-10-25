# Stage 3 — Real Bedrock Supervisor

HeatShift now supports two execution modes:

## 1. Local deterministic mode
Reliable for development and judging fallback.

Endpoint:
`POST /api/scenario/heat-spike`

## 2. Real Bedrock + Strands mode
The LLM chooses tools at runtime, while the deterministic tools retain
safety, scheduling, validation, and approval authority.

Endpoint:
`POST /api/agent/bedrock`

## Why this hybrid is important

The AI may choose:
- when to retrieve state;
- when to assess;
- when to plan;
- which tool to invoke next;
- how to explain the validated decision.

The AI may NOT:
- create or alter a safety rule;
- publish an unvalidated schedule;
- approve a plan;
- fabricate WBGT;
- convert the exposure proxy into a medical probability.

## Install AWS mode

```powershell
pip install -e ".[aws,dev]"
```

The Strands documentation uses Amazon Bedrock by default and requires AWS
credentials with Bedrock model invocation permissions.

For the hackathon AWS environment, use the credentials/session mechanism
provided by the organisers. Do not hard-code credentials in the project.

Optionally set:

```powershell
$env:AWS_REGION="ap-southeast-1"
$env:HEATSHIFT_BEDROCK_MODEL_ID="global.anthropic.claude-sonnet-4-6"
```

Use a model ID that is actually enabled in the hackathon AWS account.

## Check configuration

Run the app and open:

`http://localhost:8080/api/agent/status`

## Run real AI mode

Open `http://localhost:8080/docs`

Use:
`POST /api/agent/bedrock`

Request body:

```json
{
  "event": "WBGT_RISE",
  "use_simulated_heat": true,
  "scenario_index": 2
}
```

For competition reliability, keep the local deterministic endpoint available
even after AWS mode is working.
