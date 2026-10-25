"""
AWS AgentCore Runtime entrypoint.

The deterministic HeatShift agent is the authoritative orchestration loop.
An LLM can be added later for conversational UX, but safety constraints and
schedule validation stay deterministic.
"""
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from heatshift.agent import HeatShiftSupervisor

app = BedrockAgentCoreApp()

@app.entrypoint
def handler(payload, context=None):
    event = str(payload.get("event", "WBGT_RISE"))
    use_simulated = bool(payload.get("use_simulated_heat", True))
    scenario_index = int(payload.get("scenario_index", 2))
    decision = HeatShiftSupervisor().run(
        event=event,
        use_simulated_heat=use_simulated,
        scenario_index=scenario_index,
    )
    return decision.model_dump(mode="json")

if __name__ == "__main__":
    app.run()
