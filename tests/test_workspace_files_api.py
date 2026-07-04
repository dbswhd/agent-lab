"""Workspace Files API — roots/list/read/write + safety (mock-only)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def _make_session(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    binding_path: str | None,
    permissions: dict | None = None,
) -> tuple[TestClient, str, Path]:
    """Wire SESSIONS_DIR under a temp repo and seed one session's run.json."""
    repo = tmp_path / "repo"
    sessions_dir = repo / "sessions"
    sid = "sess-1"
    folder = sessions_dir / sid
    (folder / "attachments").mkdir(parents=True)

    # Repo contents to browse: a tracked file + dirs that must be excluded.
    (repo / "src").mkdir()
    (repo / "src" / "foo.py").write_text("print('hi')\n", encoding="utf-8")
    (repo / ".git").mkdir()
    (repo / "node_modules").mkdir()

    run_json = {
        "topic": "t",
        "permissions": permissions or {},
    }
    if binding_path is not None:
        run_json["workspace_binding"] = {"path": binding_path, "label": "repo"}
    (folder / "run.json").write_text(json.dumps(run_json), encoding="utf-8")

    # project_root() / agent-lab root → temp repo (isolates resolve_workspace_roots).
    monkeypatch.setenv("AGENT_LAB_ROOT", str(repo))
    monkeypatch.setenv("AGENT_LAB_DEV_ROOT", str(repo))
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    monkeypatch.setattr("app.server.deps.SESSIONS_DIR", sessions_dir)
    monkeypatch.setattr("agent_lab.workspace.files.SESSIONS_DIR", sessions_dir)

    from app.server.main import app

    return TestClient(app), sid, repo


def test_roots_primary_is_binding(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    client, sid, _ = _make_session(tmp_path, monkeypatch, binding_path=str(repo))
    res = client.get(f"/api/sessions/{sid}/files/roots")
    assert res.status_code == 200
    roots = res.json()["roots"]
    ids = {r["root_id"] for r in roots}
    assert "session" in ids
    workspace = [r for r in roots if r["kind"] == "workspace"]
    assert workspace, "expected a workspace root"
    primary = [r for r in roots if r["is_primary"]]
    assert len(primary) == 1
    assert primary[0]["kind"] == "workspace"
    # root_ids are unique.
    assert len(ids) == len(roots)


def test_list_dir_excludes_vcs_and_other_sessions(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    client, sid, _ = _make_session(tmp_path, monkeypatch, binding_path=str(repo))
    roots = client.get(f"/api/sessions/{sid}/files/roots").json()["roots"]
    ws = next(r for r in roots if r["kind"] == "workspace")
    res = client.get(f"/api/sessions/{sid}/files?root_id={ws['root_id']}&path=")
    assert res.status_code == 200
    names = {e["name"] for e in res.json()["entries"]}
    assert "src" in names
    assert ".git" not in names
    assert "node_modules" not in names
    # The agent-lab SESSIONS_DIR child must never be listed (cross-session leak).
    assert "sessions" not in names


def test_read_text_file(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    client, sid, _ = _make_session(tmp_path, monkeypatch, binding_path=str(repo))
    ws = next(r for r in client.get(f"/api/sessions/{sid}/files/roots").json()["roots"] if r["kind"] == "workspace")
    res = client.get(f"/api/sessions/{sid}/files/content?root_id={ws['root_id']}&path=src/foo.py")
    assert res.status_code == 200
    body = res.json()
    assert body["kind"] == "text"
    assert "print" in body["content"]
    assert body["truncated"] is False


def test_read_diff_file_as_text(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    client, sid, _ = _make_session(tmp_path, monkeypatch, binding_path=str(repo))
    (repo / "src" / "change.diff").write_text(
        "@@ -1 +1 @@\n-old\n+new PHASE2A_DIFF_OK\n",
        encoding="utf-8",
    )
    ws = next(r for r in client.get(f"/api/sessions/{sid}/files/roots").json()["roots"] if r["kind"] == "workspace")
    res = client.get(f"/api/sessions/{sid}/files/content?root_id={ws['root_id']}&path=src/change.diff")
    assert res.status_code == 200
    body = res.json()
    assert body["kind"] == "text"
    assert "PHASE2A_DIFF_OK" in body["content"]


def test_path_traversal_rejected(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    client, sid, _ = _make_session(tmp_path, monkeypatch, binding_path=str(repo))
    ws = next(r for r in client.get(f"/api/sessions/{sid}/files/roots").json()["roots"] if r["kind"] == "workspace")
    res = client.get(f"/api/sessions/{sid}/files?root_id={ws['root_id']}&path=../../../../etc")
    assert res.status_code == 403


def test_write_attachments_ok(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    client, sid, _ = _make_session(tmp_path, monkeypatch, binding_path=str(repo))
    res = client.put(
        f"/api/sessions/{sid}/files/content",
        json={"root_id": "session", "path": "attachments/note.md", "content": "# hi"},
    )
    assert res.status_code == 200
    assert res.json()["ok"] is True
    # Read it back.
    got = client.get(f"/api/sessions/{sid}/files/content?root_id=session&path=attachments/note.md")
    assert got.json()["content"] == "# hi"


def test_write_outside_attachments_rejected(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    client, sid, _ = _make_session(tmp_path, monkeypatch, binding_path=str(repo))
    # run.json under session root but outside attachments/ → 409.
    res = client.put(
        f"/api/sessions/{sid}/files/content",
        json={"root_id": "session", "path": "run.json", "content": "{}"},
    )
    assert res.status_code == 409
    detail = res.json()["detail"]
    assert detail


def test_write_repo_file_rejected(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    client, sid, _ = _make_session(tmp_path, monkeypatch, binding_path=str(repo))
    ws = next(r for r in client.get(f"/api/sessions/{sid}/files/roots").json()["roots"] if r["kind"] == "workspace")
    res = client.put(
        f"/api/sessions/{sid}/files/content",
        json={"root_id": ws["root_id"], "path": "src/foo.py", "content": "x"},
    )
    assert res.status_code == 409


def test_binding_missing_marked(tmp_path, monkeypatch):
    client, sid, _ = _make_session(tmp_path, monkeypatch, binding_path=str(tmp_path / "does-not-exist"))
    roots = client.get(f"/api/sessions/{sid}/files/roots").json()["roots"]
    missing = [r for r in roots if r.get("missing")]
    assert missing, "broken binding should be marked missing"
    # A non-missing root must still be primary (fallback).
    primary = [r for r in roots if r["is_primary"]]
    assert len(primary) == 1
    assert primary[0]["missing"] is False


def test_no_binding_falls_back_to_project_root(tmp_path, monkeypatch):
    client, sid, _ = _make_session(tmp_path, monkeypatch, binding_path=None)
    roots = client.get(f"/api/sessions/{sid}/files/roots").json()["roots"]
    # At minimum session + the AGENT_LAB_ROOT workspace root.
    assert any(r["kind"] == "workspace" and not r["missing"] for r in roots)
    assert sum(1 for r in roots if r["is_primary"]) == 1


def test_unknown_root_id_404(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    client, sid, _ = _make_session(tmp_path, monkeypatch, binding_path=str(repo))
    res = client.get(f"/api/sessions/{sid}/files?root_id=ws-deadbeef&path=")
    assert res.status_code == 404


def test_raw_serves_image_bytes(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    client, sid, _ = _make_session(tmp_path, monkeypatch, binding_path=str(repo))
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
    (repo / "sessions" / sid / "attachments" / "pic.png").write_bytes(png)
    res = client.get(f"/api/sessions/{sid}/files/raw?root_id=session&path=attachments/pic.png")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("image/png")
    assert res.content == png


def test_raw_rejects_traversal(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    client, sid, _ = _make_session(tmp_path, monkeypatch, binding_path=str(repo))
    res = client.get(f"/api/sessions/{sid}/files/raw?root_id=session&path=../../../etc/hosts")
    assert res.status_code == 403


def test_label_collision_disambiguated():
    """Same-label roots get a path suffix; root_ids stay unique."""
    from agent_lab.workspace.files import RootInfo, _disambiguate_labels

    roots = [
        RootInfo("session", "session", "session", Path("/s"), False, False),
        RootInfo("ws-a", "proj", "workspace", Path("/a/proj"), True, False),
        RootInfo("ws-b", "proj", "workspace", Path("/b/proj"), False, False),
    ]
    _disambiguate_labels(roots)
    labels = [r.label for r in roots if r.kind == "workspace"]
    assert labels[0] != labels[1]
    assert "/a/proj" in labels[0]
    assert "/b/proj" in labels[1]
