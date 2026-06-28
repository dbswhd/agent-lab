"""LC-oracle mock-first verification for merged plan actions."""

from __future__ import annotations

from pathlib import Path

from agent_lab.plan.actions import PlanAction
from agent_lab.plan.execute_merge import oracle_verify, verify_after_merge


def _action(verify: str) -> PlanAction:
    return PlanAction(
        index=1,
        what="Update app marker",
        where="`src/app.py`",
        verify=verify,
        refs=(),
        raw="",
        kind="now",
    )


def test_oracle_verify_skips_missing_verify(tmp_path: Path):
    result = oracle_verify(
        _action("-"),
        ["src/app.py"],
        workspace_root=tmp_path,
    )

    assert result["verdict"] == "skipped"
    assert result["detail"] == "verify field missing"
    assert result["checked_paths"] == []


def test_oracle_verify_mock_passes_when_literal_present(tmp_path: Path):
    target = tmp_path / "src" / "app.py"
    target.parent.mkdir()
    target.write_text("READY = True\n", encoding="utf-8")

    result = oracle_verify(
        _action("`src/app.py` contains `READY`"),
        ["src/app.py"],
        workspace_root=tmp_path,
    )

    assert result["verdict"] == "pass"
    assert "READY" in result["detail"]
    assert result["verify_criterion"] == "`src/app.py` contains `READY`"
    assert result["checked_paths"] == ["src/app.py"]


def test_oracle_verify_mock_fails_when_literal_missing(tmp_path: Path):
    target = tmp_path / "src" / "app.py"
    target.parent.mkdir()
    target.write_text("NOTREADY = True\n", encoding="utf-8")

    result = oracle_verify(
        _action("`src/app.py` contains `READY`"),
        ["src/app.py"],
        workspace_root=tmp_path,
    )

    assert result["verdict"] == "fail"
    assert "READY" in result["detail"]
    assert result["checked_paths"] == ["src/app.py"]


def test_oracle_verify_uses_injected_oracle_call(tmp_path: Path):
    target = tmp_path / "src" / "app.py"
    target.parent.mkdir()
    target.write_text("READY = True\n", encoding="utf-8")
    prompts: list[str] = []

    def oracle_call(prompt: str) -> str:
        prompts.append(prompt)
        return "FAIL: injected oracle found a policy issue"

    result = oracle_verify(
        {"action_verify": "`src/app.py` contains `READY`"},
        ["src/app.py"],
        workspace_root=tmp_path,
        oracle_call=oracle_call,
    )

    assert result["verdict"] == "fail"
    assert "injected oracle" in result["detail"]
    assert result.get("source") == "live"
    assert len(prompts) == 1
    assert "Verification criterion:" in prompts[0]
    assert "READY = True" in prompts[0]


def test_oracle_verify_session_folder_defaults_to_parent_workspace(tmp_path: Path):
    session = tmp_path / "session"
    session.mkdir()
    target = tmp_path / "src" / "app.py"
    target.parent.mkdir()
    target.write_text("DONE\n", encoding="utf-8")

    result = oracle_verify(
        _action("`src/app.py` contains `DONE`"),
        ["src/app.py"],
        session_folder=session,
    )

    assert result["verdict"] == "pass"
    assert result["checked_paths"] == ["src/app.py"]


def test_verify_after_merge_wraps_oracle_pass(tmp_path: Path):
    target = tmp_path / "src" / "app.py"
    target.parent.mkdir()
    target.write_text("DONE\n", encoding="utf-8")

    result = verify_after_merge(
        _action("`src/app.py` contains `DONE`"),
        ["src/app.py"],
        workspace_root=tmp_path,
        verify_retries=1,
    )

    assert result["status"] == "passed"
    assert result["verify_retries"] == 1
    assert result["oracle"]["verdict"] == "pass"


def test_verify_after_merge_wraps_oracle_fail(tmp_path: Path):
    target = tmp_path / "src" / "app.py"
    target.parent.mkdir()
    target.write_text("pending\n", encoding="utf-8")

    result = verify_after_merge(
        _action("`src/app.py` contains `DONE`"),
        ["src/app.py"],
        workspace_root=tmp_path,
    )

    assert result["status"] == "failed"
    assert result["verify_retries"] == 0
    assert result["oracle"]["verdict"] == "fail"


def test_verify_after_merge_passes_oracle_call_to_oracle_verify(tmp_path: Path):
    target = tmp_path / "src" / "app.py"
    target.parent.mkdir()
    target.write_text("DONE\n", encoding="utf-8")
    seen: list[str] = []

    result = verify_after_merge(
        _action("`src/app.py` contains `DONE`"),
        ["src/app.py"],
        workspace_root=tmp_path,
        oracle_call=lambda prompt: seen.append(prompt) or "PASS: injected",
    )

    assert result["status"] == "passed"
    assert result["oracle"]["verdict"] == "pass"
    assert len(seen) == 1
    assert "DONE" in seen[0]
