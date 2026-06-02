"""Plan provenance ref extraction."""

from agent_lab.plan_provenance import extract_plan_provenance, validate_plan_refs


def test_extract_plan_provenance_sections():
    plan = """## 합의된 점
- Freeze baseline (ref: chat.jsonl#L42)
## 쟁점 / 미결정
- Open item (ref: chat.jsonl#L55)
"""
    prov = extract_plan_provenance(plan)
    assert "합의된 점" in prov
    assert prov["합의된 점"][0]["line"] == 42


def test_validate_plan_refs_out_of_range():
    plan = "- Bad (ref: chat.jsonl#L999)"
    issues = validate_plan_refs(plan, chat_line_count=10)
    assert len(issues) == 1
    assert issues[0]["reason"] == "out_of_range"
