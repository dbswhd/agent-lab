#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = ["fastapi>=0.115"]
# ///

# ─── How to run ───
# 1. Install uv: curl -LsSf https://astral.sh/uv/install.sh | sh
# 2. Run: uv run scripts/mission_authority_cohort_matrix.py
# 3. Or: chmod +x scripts/mission_authority_cohort_matrix.py && ./scripts/mission_authority_cohort_matrix.py
# ──────────────────

"""Bounded Mission authority cohort matrix and route probes.

This module does not activate a cohort. Callers provide temporary environment
setters and session roots; production defaults remain unchanged.
"""

from __future__ import annotations

import json
import subprocess
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Final, Protocol

from agent_lab.mission.dual_write import (
    mission_authority_enabled,
    plan_write_authority_enabled,
)
from agent_lab.plan.execute_worktree import create_exec_worktree
from agent_lab.run.meta import read_run_meta
from agent_lab.run.meta import patch_run_meta
from agent_lab.subprocess_env import subprocess_env


class RouteClient(Protocol):
    def post(self, url: str, *, json: dict[str, object]) -> Response: ...


class Response(Protocol):
    @property
    def status_code(self) -> int: ...

    def json(self) -> dict[str, object]: ...


class HttpJson:
    def __init__(self, port: int) -> None:
        self.base = f"http://127.0.0.1:{port}"

    def request(
        self,
        method: str,
        path: str,
        body: dict[str, object] | None = None,
    ) -> tuple[int, dict[str, object]]:
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(f"{self.base}{path}", data=data, method=method)
        if data is not None:
            request.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(request, timeout=20) as response:  # noqa: S310
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read())

    def healthy(self) -> bool:
        try:
            status, _ = self.request("GET", "/api/health")
        except (urllib.error.URLError, OSError):
            return False
        return status == 200


@dataclass(frozen=True, slots=True)
class CohortRow:
    name: str
    plan_authority: bool
    inbox_authority: bool
    overlap: bool


@dataclass(frozen=True, slots=True)
class RouteProbe:
    cohort: str
    plan_authority: bool
    inbox_authority: bool
    plan_status: int
    plan_bridge_reason: str
    inbox_create_status: int
    inbox_resolve_status: int
    duplicate_status: int
    malformed_status: int
    legacy_inbox_written: bool


@dataclass(frozen=True, slots=True)
class ExecutionSeed:
    folder: Path
    repo: Path
    execution_id: str
    verify: str


AUTHORITY_MATRIX: Final = (
    CohortRow("plan-only", True, False, False),
    CohortRow("inbox-only", False, True, False),
    CohortRow("both", True, True, True),
    CohortRow("neither", False, False, False),
)


def git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(cwd), *args],
        check=True,
        capture_output=True,
        text=True,
        env=subprocess_env(),
    )
    return result.stdout.strip()


def seed_repo(root: Path, name: str) -> Path:
    repo = root / name
    repo.mkdir()
    git(repo, "init", "-b", "main")
    (repo / "src").mkdir()
    (repo / "src" / "app.py").write_text("v1\n", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "init")
    return repo


def seed_execution(seed: ExecutionSeed) -> None:
    worktree = create_exec_worktree(
        seed.folder,
        exec_id=seed.execution_id,
        git_root=seed.repo,
        action_key="now:1",
        session_id=seed.folder.name,
    )
    (worktree.worktree_path / "src" / "app.py").write_text("v2\n", encoding="utf-8")
    git(worktree.worktree_path, "add", "-A")
    git(worktree.worktree_path, "commit", "-m", "execution marker")
    row = {
        "id": seed.execution_id,
        "status": "pending_approval",
        "isolation_effective": "worktree",
        "action_index": 1,
        "action_kind": "now",
        "action_key": "now:1",
        "action_what": "ship marker",
        "action_where": "`src/app.py`",
        "action_verify": seed.verify,
        "expected_paths": ["src/app.py"],
        "source_touched_paths": ["src/app.py"],
        "touched_paths": ["src/app.py"],
        "exec_commit_sha": git(worktree.worktree_path, "rev-parse", "HEAD"),
        **worktree.to_dict(),
    }

    def _patch(run: dict[str, object]) -> dict[str, object]:
        run["executions"] = [row]
        return run

    patch_run_meta(seed.folder, _patch)


def apply_cohort(setenv: Callable[[str, str], None], cohort_name: str) -> None:
    """Apply one matrix row to an isolated process environment."""
    rows = {row.name: row for row in AUTHORITY_MATRIX}
    row = rows[cohort_name]
    setenv("AGENT_LAB_MISSION_DUAL_WRITE", "1")
    setenv("AGENT_LAB_MISSION_PLAN_WRITE_AUTHORITY", "1")
    setenv("AGENT_LAB_MISSION_EXECUTION_WRITE_AUTHORITY", "1")
    setenv("AGENT_LAB_MISSION_AUTHORITY", "1")
    setenv("AGENT_LAB_MISSION_DUAL_WRITE_SESSIONS", cohort_name if row.plan_authority else "")
    setenv("AGENT_LAB_MISSION_AUTHORITY_SESSIONS", cohort_name if row.inbox_authority else "")


def _seed_session(sessions: Path, session_id: str) -> Path:
    folder = sessions / session_id
    folder.mkdir()
    (folder / "plan.md").write_text("# Plan\n\n- ship\n", encoding="utf-8")
    (folder / "run.json").write_text(
        json.dumps(
            {
                "topic": "ship",
                "plan_workflow": {"enabled": True, "phase": "HUMAN_PENDING"},
            }
        ),
        encoding="utf-8",
    )
    return folder


def route_probe(client: RouteClient, sessions: Path, session_id: str) -> RouteProbe:
    """Exercise plan and Inbox production routes for one matrix cell."""
    folder = _seed_session(sessions, session_id)
    plan = client.post(
        f"/api/sessions/{session_id}/plan/approve",
        json={"goal": "ship"},
    )
    plan_body = plan.json()
    bridge = plan_body.get("mission_dual_write")
    bridge_reason = str(bridge.get("reason") or "") if isinstance(bridge, dict) else ""

    created = client.post(
        f"/api/sessions/{session_id}/inbox/items",
        json={
            "kind": "question",
            "prompt": "Proceed?",
            "source": "mcp",
            "options": [{"id": "go", "label": "Go"}],
        },
    )
    created_body = created.json()
    item = created_body.get("item")
    item_id = str(item.get("id") or "") if isinstance(item, dict) else ""
    answer = {
        "selected": ["go"],
        "expected_version": 0,
        "append_chat": False,
    }
    resolved = client.post(
        f"/api/sessions/{session_id}/inbox/{item_id}/resolve",
        json=answer,
    )
    duplicate = client.post(
        f"/api/sessions/{session_id}/inbox/{item_id}/resolve",
        json=answer,
    )
    malformed = client.post(
        f"/api/sessions/{session_id}/inbox/{item_id}/resolve",
        json={"expected_version": -1},
    )
    return RouteProbe(
        cohort=session_id,
        plan_authority=plan_write_authority_enabled(folder),
        inbox_authority=mission_authority_enabled(folder),
        plan_status=plan.status_code,
        plan_bridge_reason=bridge_reason,
        inbox_create_status=created.status_code,
        inbox_resolve_status=resolved.status_code,
        duplicate_status=duplicate.status_code,
        malformed_status=malformed.status_code,
        legacy_inbox_written="human_inbox" in read_run_meta(folder),
    )


def main() -> int:
    print(json.dumps([asdict(row) for row in AUTHORITY_MATRIX], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
