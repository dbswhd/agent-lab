"""ABSORB Wave 2 remaining — status / notify / monitor / fork."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_lab.evidence_ledger import read_evidence_tail
from agent_lab.evidence_monitor import (
    maybe_record_merge_checks_monitor,
    record_monitor_event,
)
from agent_lab.run.meta import read_run_meta, write_run_meta
from agent_lab.runtime.snapshot import build_runtime_snapshot
from agent_lab.session.fork import fork_session

ROOT = Path(__file__).resolve().parents[1]


def _session(tmp_path: Path, name: str = "sess_w2") -> Path:
    folder = tmp_path / name
    folder.mkdir()
    write_run_meta(
        folder,
        {
            "_session_id": folder.name,
            "workspace_preset": "agent-lab",
            "session_template": "general",
            "topic": "wave2 topic",
        },
    )
    (folder / "topic.txt").write_text("wave2 topic\n", encoding="utf-8")
    (folder / "plan.md").write_text("# Plan\n\n- do thing\n", encoding="utf-8")
    (folder / "chat.jsonl").write_text(
        '{"role":"user","text":"hi"}\n{"role":"assistant","text":"yo"}\n',
        encoding="utf-8",
    )
    return folder


def test_status_line_in_runtime_snapshot(tmp_path: Path) -> None:
    folder = _session(tmp_path)
    write_run_meta(
        folder,
        {
            **read_run_meta(folder),
            "schedule_sandbox": True,
            "executions": [
                {
                    "id": "ex1",
                    "status": "pending_approval",
                    "isolation_effective": "worktree",
                    "sandbox_intent": "docker",
                }
            ],
        },
    )
    snap = build_runtime_snapshot(folder)
    line = snap["status_line"]
    assert line["worktree"] is True
    assert line["schedule_sandbox"] is True
    assert line["isolation"] == "worktree"
    assert line["sandbox_intent"] == "docker"


def test_record_monitor_event(tmp_path: Path) -> None:
    folder = _session(tmp_path)
    row = record_monitor_event(
        folder,
        kind="ci_status",
        detail="pytest failed",
        refs=["ci"],
        ok=False,
    )
    assert row["phase"] == "MONITOR"
    assert row["kind"] == "ci_status"
    tail = read_evidence_tail(folder)
    assert any(e.get("phase") == "MONITOR" for e in tail)


def test_merge_checks_monitor_dedup(tmp_path: Path) -> None:
    folder = _session(tmp_path)
    payload = {
        "checks": [
            {"id": "oracle_verdict", "ok": False, "detail": "FAIL"},
        ]
    }
    first = maybe_record_merge_checks_monitor(folder, payload)
    second = maybe_record_merge_checks_monitor(folder, payload)
    assert first is not None
    assert second is None
    assert read_run_meta(folder).get("monitor_merge_checks_fp")


def test_fork_session_copies_plan_not_executions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "agent_lab.session.fork.active_sessions_dir",
        lambda: tmp_path,
    )

    source = _session(tmp_path, "src_fork")
    write_run_meta(
        source,
        {
            **read_run_meta(source),
            "executions": [{"id": "ex1", "status": "pending_approval"}],
            "human_inbox": {"items": [{"id": "q1", "status": "pending"}]},
            "steer_queue": [{"id": "s1", "text": "x"}],
        },
    )

    result = fork_session(source, copy_plan=True, chat_tail=10)
    dest = Path(result["folder"])
    assert dest.is_dir()
    assert dest.name != source.name
    assert (dest / "plan.md").is_file()
    assert "do thing" in (dest / "plan.md").read_text(encoding="utf-8")
    meta = read_run_meta(dest)
    assert meta.get("forked_from", {}).get("session_id") == source.name
    assert not meta.get("executions")
    assert "human_inbox" not in meta
    assert "steer_queue" not in meta
    assert result["chat_lines"] == 2


def test_wave2_frontend_surfaces_exist() -> None:
    assert (ROOT / "web/src/components/SessionStatusLine.tsx").is_file()
    assert (ROOT / "web/src/utils/sessionStatusLine.ts").is_file()
    assert (ROOT / "web/src/utils/notifyNeedsInput.ts").is_file()
    view = (ROOT / "web/src/components/RoomChatView.tsx").read_text(encoding="utf-8")
    assert "SessionStatusLine" in view
    assert "notifyNeedsInputIfBackground" in view
    menu = (ROOT / "web/src/components/SessionContextMenu.tsx").read_text(
        encoding="utf-8"
    )
    assert "fork" in menu
    assert "session-menu-fork" in menu
    timeline = (ROOT / "web/src/components/EvidenceTimeline.tsx").read_text(
        encoding="utf-8"
    )
    assert "MONITOR" in timeline
