from agent_lab.plan.sync_summary import summarize_plan_changes


def test_summarize_new_plan():
    assert summarize_plan_changes("", "## 합의된 점\n- a") == "plan.md 신규 작성"


def test_summarize_unchanged():
    plan = "## 합의된 점\n- same"
    assert "동일" in summarize_plan_changes(plan, plan)


def test_summarize_section_changes():
    old = "## 합의된 점\n- before\n\n## 지금 실행\n1. old"
    new = "## 합의된 점\n- after\n\n## 지금 실행\n1. new"
    summary = summarize_plan_changes(old, new)
    assert "합의된 점" in summary
    assert "지금 실행" in summary
