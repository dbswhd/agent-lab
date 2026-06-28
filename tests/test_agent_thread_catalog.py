from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from agent_lab.agent.thread_catalog import list_agent_threads, relative_last_label
from agent_lab.agent.thread_resume import build_agent_thread_resume_block
from agent_lab.session.setup import seed_session_setup, session_setup_options


def test_relative_last_label_minutes():
    now = datetime.now(timezone.utc)
    past = now - timedelta(minutes=5)
    label = relative_last_label(past)
    assert label.endswith("m")


def test_list_agent_threads_from_chat(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_LAB_SESSIONS_DIR", str(tmp_path))
    folder = tmp_path / "2026-06-01-demo"
    folder.mkdir()
    (folder / "topic.txt").write_text("Demo topic\n", encoding="utf-8")
    (folder / "meta.json").write_text(
        json.dumps({"created_at": "2026-06-01T10:00:00+00:00"}),
        encoding="utf-8",
    )
    chat_lines = [
        {"role": "user", "content": "hi", "ts": "2026-06-01T10:01:00+00:00"},
        {"role": "agent", "agent": "cursor", "content": "hello", "ts": "2026-06-01T10:02:00+00:00"},
        {"role": "agent", "agent": "codex", "content": "ack", "ts": "2026-06-01T10:03:00+00:00"},
    ]
    (folder / "chat.jsonl").write_text(
        "\n".join(json.dumps(row) for row in chat_lines) + "\n",
        encoding="utf-8",
    )

    threads = list_agent_threads(sessions_root=tmp_path)
    assert threads["cursor"][0]["id"] == "2026-06-01-demo"
    assert threads["cursor"][0]["label"] == "Demo topic"
    assert threads["cursor"][0]["msgs"] == 1
    assert threads["codex"][0]["msgs"] == 1
    assert threads["claude"] == []


def test_session_setup_options_includes_agent_threads(monkeypatch, tmp_path):
    monkeypatch.setenv("AGENT_LAB_ROOT", str(tmp_path))
    opts = session_setup_options()
    assert "agent_threads" in opts
    assert set(opts["agent_threads"].keys()) == {"cursor", "codex", "claude"}


def test_seed_session_setup_persists_thread_bindings(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_LAB_ROOT", str(tmp_path))
    folder = tmp_path / "sess"
    folder.mkdir()
    seed_session_setup(
        folder,
        workspace_id="agent-lab",
        session_template="general",
        agent_thread_bindings={"cursor": "2026-06-01-old", "codex": "new"},
    )
    run = json.loads((folder / "run.json").read_text(encoding="utf-8"))
    assert run["agent_thread_bindings"]["cursor"] == "2026-06-01-old"
    assert run["agent_thread_bindings"]["codex"] == "new"


def test_build_agent_thread_resume_block(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_LAB_SESSIONS_DIR", str(tmp_path))
    src = tmp_path / "2026-06-01-old"
    src.mkdir()
    (src / "topic.txt").write_text("Old work\n", encoding="utf-8")
    (src / "chat.jsonl").write_text(
        json.dumps(
            {
                "role": "agent",
                "agent": "cursor",
                "content": "Prior fix shipped",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    block = build_agent_thread_resume_block(
        "cursor",
        {"agent_thread_bindings": {"cursor": "2026-06-01-old"}},
    )
    assert "2026-06-01-old" in block
    assert "Prior fix shipped" in block
