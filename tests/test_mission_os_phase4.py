"""Mission OS Phase 4 — skill drafts from verify PASS."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent_lab.context.bundle import build_context_bundle
from agent_lab.human_inbox import pending_inbox_items
from agent_lab.run.meta import read_run_meta
from agent_lab.skill_drafts import (
    build_session_skills_block,
    maybe_create_skill_draft_from_verify,
    render_skill_markdown,
    session_auto_allowed,
    slug_for_execution,
    verify_evidence_passed,
)
from app.server.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def session_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    import agent_lab.session as session_mod
    import app.server.deps as deps_mod

    folder = tmp_path / "skill-sess"
    folder.mkdir()
    (folder / "topic.txt").write_text("skills\n", encoding="utf-8")
    monkeypatch.setattr(session_mod, "SESSIONS_DIR", tmp_path)
    monkeypatch.setattr(deps_mod, "SESSIONS_DIR", tmp_path)
    monkeypatch.setenv("AGENT_LAB_SKILL_DRAFTS", "1")
    return folder


def _execution(**overrides: object) -> dict:
    row = {
        "id": "exec-1",
        "action_index": 2,
        "action_verify": "make test-fast",
        "draft_summary": "Docs-only README tweak",
        "source_touched_paths": ["docs/README.md"],
    }
    row.update(overrides)
    return row


def _evidence_pass() -> dict:
    return {"status": "passed", "oracle": {"verdict": "pass", "detail": "tests green"}}


def test_verify_evidence_passed() -> None:
    assert verify_evidence_passed(_evidence_pass()) is True
    assert verify_evidence_passed({"status": "failed", "oracle": {"verdict": "fail"}}) is False


def test_slug_for_execution() -> None:
    slug = slug_for_execution(_execution())
    assert slug.startswith("verify-2-")


def test_session_auto_assistant_vs_dev_code() -> None:
    exec_row = _execution(source_touched_paths=["src/foo.py"])
    assert session_auto_allowed({"gate_profile": "assistant"}, exec_row) is True
    assert session_auto_allowed({"gate_profile": "dev"}, exec_row) is False
    assert (
        session_auto_allowed(
            {"gate_profile": "dev"},
            _execution(source_touched_paths=["docs/a.md"]),
        )
        is True
    )


def test_maybe_create_skill_draft_assistant(
    session_folder: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "agent_lab.gateway.telegram_adapter.notify_inbox_pending",
        lambda *_a, **_k: None,
    )
    (session_folder / "run.json").write_text(
        json.dumps({"gate_profile": "assistant"}) + "\n",
        encoding="utf-8",
    )
    row = maybe_create_skill_draft_from_verify(
        session_folder,
        _execution(),
        _evidence_pass(),
    )
    assert row is not None
    assert row["status"] == "session_only"
    draft_path = session_folder / str(row["draft_path"])
    assert draft_path.is_file()
    session_skill = session_folder / "skills" / row["slug"] / "SKILL.md"
    assert session_skill.is_file()
    run = read_run_meta(session_folder)
    pending = [i for i in pending_inbox_items(run) if i.get("kind") == "skill_draft"]
    assert len(pending) == 1


def test_promote_skill_draft_api(
    client: TestClient,
    session_folder: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "agent_lab.gateway.telegram_adapter.notify_inbox_pending",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        "agent_lab.skill_drafts.workspace_skills_root",
        lambda: tmp_path / "skills",
    )
    (session_folder / "run.json").write_text(
        json.dumps({"gate_profile": "assistant"}) + "\n",
        encoding="utf-8",
    )
    row = maybe_create_skill_draft_from_verify(
        session_folder,
        _execution(),
        _evidence_pass(),
    )
    assert row is not None
    sid = session_folder.name
    r = client.post(f"/api/sessions/{sid}/skills/drafts/{row['id']}/promote")
    assert r.status_code == 200
    assert r.json()["draft"]["status"] == "promoted"
    promoted = tmp_path / "skills" / row["slug"] / "SKILL.md"
    assert promoted.is_file()


def test_context_bundle_includes_session_skills(session_folder: Path) -> None:
    content = render_skill_markdown(
        slug="verify-lesson",
        execution=_execution(),
        evidence=_evidence_pass(),
    )
    skill_path = session_folder / "skills" / "verify-lesson" / "SKILL.md"
    skill_path.parent.mkdir(parents=True, exist_ok=True)
    skill_path.write_text(content, encoding="utf-8")
    run_meta = {
        "_session_folder": str(session_folder),
        "session_skills": ["verify-lesson"],
    }
    block = build_session_skills_block(run_meta)
    assert "Session skills" in block
    assert "verify-lesson" in block

    bundle = build_context_bundle(
        "topic",
        [],
        "claude",
        run_meta=run_meta,
    )
    assert "verify-lesson" in bundle.constraints
