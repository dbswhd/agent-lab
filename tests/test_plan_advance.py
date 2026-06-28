"""Plan advance after thin execute approval."""

from __future__ import annotations

from agent_lab.plan.advance import advance_plan_after_approval, advance_plan_md


SAMPLE = """## 합의된 점
- example

## 지금 실행
1.
   - 무엇을: first now task
   - 어디서: `a.py`
   - 검증: ok

## 실행 순서 (이후)
1.
   - 무엇을: first roadmap task
   - 어디서: `b.py`
   - 검증: ok
2. Human gate line. (ref: chat.jsonl#L1)

3.
   - 무엇을: third roadmap task
   - 어디서: `c.py`
   - 검증: ok
"""


def test_advance_now_promotes_next_roadmap_executable():
    new_plan, meta = advance_plan_md(SAMPLE, kind="now", index=1)
    assert meta["changed"] is True
    assert meta["promoted_action_key"] == "now:1"
    assert "first now task" not in new_plan
    assert "first roadmap task" in new_plan
    assert "## 지금 실행" in new_plan
    body_now = new_plan.split("## 실행 순서")[0]
    assert "first roadmap task" in body_now
    assert "third roadmap task" in new_plan
    assert new_plan.index("Human gate") < new_plan.index("third roadmap")


def test_advance_roadmap_removes_without_promoting_now():
    new_plan, meta = advance_plan_md(SAMPLE, kind="roadmap", index=3)
    assert meta["changed"] is True
    assert meta["promoted_action_key"] is None
    assert "first now task" in new_plan
    assert "third roadmap task" not in new_plan
    assert "first roadmap task" in new_plan


def test_advance_legacy_format():
    legacy = """## 다음에 할 일
1.
   - 무엇을: task one
   - 어디서: `one.py`
   - 검증: ok
2.
   - 무엇을: task two
   - 어디서: `two.py`
   - 검증: ok
"""
    new_plan, meta = advance_plan_md(legacy, kind="legacy", index=1)
    assert meta["changed"] is True
    assert "task one" not in new_plan
    assert "task two" in new_plan
    assert "task one" not in new_plan
    assert "2." not in new_plan


def test_advance_plan_after_approval_writes_file(tmp_path):
    session = tmp_path / "sess"
    session.mkdir()
    (session / "plan.md").write_text(SAMPLE, encoding="utf-8")
    result = advance_plan_after_approval(
        session,
        {
            "status": "completed",
            "action_kind": "now",
            "action_index": 1,
            "action_key": "now:1",
        },
    )
    assert result["advanced"] is True
    updated = (session / "plan.md").read_text(encoding="utf-8")
    assert "first now task" not in updated
    assert "first roadmap task" in updated.split("## 실행 순서")[0]
