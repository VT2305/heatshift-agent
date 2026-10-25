from pathlib import Path

def test_bedrock_module_present():
    p = Path("heatshift/ai/bedrock_supervisor.py")
    assert p.exists()
    text = p.read_text()
    assert "propose_plan_change" in text
    assert "validate_schedule" in text
    assert "BedrockModel" in text

def test_human_approval_not_exposed_as_ai_tool():
    text = Path("heatshift/ai/strands_tools.py").read_text()
    assert "@tool\n    def approve_plan" not in text
    assert "ai_can_approve" in text
