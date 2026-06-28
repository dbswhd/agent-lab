"""MB-8 — external runner handoff JSON attach."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_lab.external_handoff import (
    attach_external_handoff,
    parse_handoff_payload,
    public_external_handoff,
    try_attach_handoff_from_external_result,
    validate_external_handoff,
)
from agent_lab.runtime.external_runner import run_external_command
from agent_lab.run.meta import patch_run_meta, read_run_meta


def _session_with_execution(folder: Path, execution_id: str = "exec-1") -> None:
    patch_run_meta(
        folder,
        lambda run: {
            **run,
            "executions": [
                {
                    "id": execution_id,
                    "status": "pending_approval",
                    "action_index": 1,
                }
            ],
        },
    )


def test_validate_external_handoff_requires_keys() -> None:
    ok, errors = validate_external_handoff({})
    assert not ok
    assert any("missing:" in err for err in errors)


def test_attach_external_handoff_persists(tmp_path: Path) -> None:
    folder = tmp_path / "sess-1"
    folder.mkdir()
    _session_with_execution(folder)
    payload = {
        "stopped_cleanly": True,
        "changed_files": ["src/foo.py"],
        "checks": [{"cmd": "make test", "exit": 0}],
        "evidence_summary": "Tests passed; ready for merge review.",
        "risks": [],
        "source": "gjc",
    }
    row = attach_external_handoff(folder, execution_id="exec-1", payload=payload)
    handoff = public_external_handoff(row)
    assert handoff is not None
    assert handoff["evidence_summary"] == payload["evidence_summary"]
    assert handoff["changed_files"] == ["src/foo.py"]
    run = read_run_meta(folder)
    stored = run["executions"][0]["external_handoff"]
    assert stored["stopped_cleanly"] is True
    assert stored["source"] == "gjc"


def test_parse_handoff_payload_from_stdout() -> None:
    payload = {
        "stopped_cleanly": True,
        "changed_files": ["a.py"],
        "checks": [{"cmd": "make test", "exit": 0}],
        "evidence_summary": "done",
        "risks": [],
    }
    text = f"runner done\n```json\n{json.dumps(payload)}\n```"
    parsed = parse_handoff_payload(text)
    assert parsed is not None
    assert parsed["evidence_summary"] == "done"


def test_try_attach_handoff_from_external_result(tmp_path: Path) -> None:
    folder = tmp_path / "sess-3"
    folder.mkdir()
    _session_with_execution(folder, execution_id="exec-3")
    handoff = {
        "stopped_cleanly": True,
        "changed_files": ["src/foo.py"],
        "checks": [{"cmd": "make test", "exit": 0}],
        "evidence_summary": "auto attached",
        "risks": [],
    }
    result = {
        "ok": True,
        "stdout": json.dumps(handoff),
    }
    attached = try_attach_handoff_from_external_result(
        folder,
        result,
        tool_id="external:gjc",
    )
    assert attached is not None
    assert attached.get("attached") is True
    run = read_run_meta(folder)
    assert run["executions"][0]["external_handoff"]["evidence_summary"] == "auto attached"


def test_run_external_command_auto_attaches_handoff(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    folder = tmp_path / "sess-4"
    folder.mkdir()
    (folder / "run.json").write_text(
        json.dumps(
            {
                "executions": [{"id": "exec-4", "status": "pending_approval", "action_index": 1}],
                "external_tools": {"enabled": ["external:handoff"]},
            }
        ),
        encoding="utf-8",
    )
    handoff = {
        "stopped_cleanly": True,
        "changed_files": [],
        "checks": [],
        "evidence_summary": "from echo",
        "risks": [],
    }
    tools_dir = tmp_path / "tools"
    tools_dir.mkdir()
    (tools_dir / "tools.yaml").write_text(
        f"""
tools:
  - id: external:handoff
    command: echo '{json.dumps(handoff)}'
    human_approve: false
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("AGENT_LAB_EXTERNAL_TOOLS", "1")
    monkeypatch.setattr(
        "agent_lab.external_tools._tools_paths",
        lambda: [tools_dir / "tools.yaml"],
    )
    result = run_external_command(folder, "external:handoff", confirm=True)
    assert result.get("ok") is True
    attach = result.get("handoff_attach") or {}
    assert attach.get("attached") is True


def test_attach_external_handoff_rejects_invalid(tmp_path: Path) -> None:
    folder = tmp_path / "sess-2"
    folder.mkdir()
    _session_with_execution(folder, execution_id="exec-2")
    with pytest.raises(ValueError, match="missing:"):
        attach_external_handoff(
            folder,
            execution_id="exec-2",
            payload={"stopped_cleanly": True},
        )
