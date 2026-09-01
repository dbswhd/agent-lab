"""Live delegate spike — worktree dry-run + external CLI handoff attach (C5)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from contextlib import nullcontext
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import patch

from agent_lab.external_handoff import public_external_handoff
from agent_lab.plan.actions import find_dry_run_action
from agent_lab.plan.execute import resolve_execution, run_dry_run
from agent_lab.plan.pending import PlanSnapshotRequired, approve_pending_plan
from agent_lab.runtime.external_runner import (
    patch_external_tools_allowlist,
    run_external_command,
)

SPIKE_MARKER = "LIVE_DELEGATE_OK"
SPIKE_REL_PATH = "src/spike.txt"
DELEGATE_TOOL_MOCK = "external:delegate-spike-mock"
DELEGATE_TOOL_CODEX = "external:codex-delegate"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(cwd), *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _git_porcelain(cwd: Path) -> str:
    return _git(cwd, "status", "--porcelain")


def _init_spike_repo(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    _git(repo, "init", "-b", "main")
    (repo / "src").mkdir(parents=True, exist_ok=True)
    (repo / SPIKE_REL_PATH).write_text("# baseline\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "delegate spike init")


def _plan_md(repo: Path) -> str:
    rel = SPIKE_REL_PATH
    return f"""## 지금 실행
1.
   - 무엇을: Append `{SPIKE_MARKER}` to {rel} via external delegate.
   - 어디서: `{rel}`
   - 검증: `{rel}` contains `{SPIKE_MARKER}`
"""


def _seed_plan_snapshot(session: Path, plan_md: str) -> None:
    action = find_dry_run_action(plan_md, 1, kind="now")
    if action is None:
        raise ValueError("plan action 1 not found")
    from agent_lab.plan.pending import ensure_plan_snapshot_approved

    try:
        ensure_plan_snapshot_approved(session, action, plan_md)
    except PlanSnapshotRequired as exc:
        approve_pending_plan(session, exc.pending_plan["id"])


def _handoff_payload(changed: list[str]) -> dict[str, Any]:
    return {
        "stopped_cleanly": True,
        "changed_files": changed,
        "checks": [{"cmd": "delegate-spike", "exit": 0}],
        "evidence_summary": f"Delegate spike attached {SPIKE_MARKER}",
        "risks": [],
    }


def _mock_tools_yaml(path: Path) -> None:
    payload = _handoff_payload([SPIKE_REL_PATH])
    emit_script = path.parent / "emit_delegate_handoff.py"
    emit_script.write_text(
        f"import json\nprint(json.dumps({payload!r}))\n",
        encoding="utf-8",
    )
    path.write_text(
        f"""
tools:
  - id: {DELEGATE_TOOL_MOCK}
    slash: /delegate-spike-mock
    label: Delegate spike mock
    human_approve: false
    cwd: worktree
    command:
      - /bin/sh
      - -c
      - 'printf "\\n{SPIKE_MARKER}\\n" >> {SPIKE_REL_PATH} && python3 {emit_script}'
""",
        encoding="utf-8",
    )


def _preflight_codex() -> dict[str, Any]:
    from agent_lab.codex.cli import is_available, resolve_codex_bin

    return {
        "available": is_available(),
        "bin": resolve_codex_bin(),
    }


def _delegate_mode() -> str:
    explicit = (os.getenv("DELEGATE_SPIKE_MODE") or "").strip().lower()
    if explicit in {"mock", "codex"}:
        return explicit
    if os.getenv("AGENT_LAB_RUN_LIVE", "").strip().lower() in {"1", "true", "yes"}:
        return "codex"
    return "mock"


def _delegate_prompt() -> str:
    rel = SPIKE_REL_PATH
    return (
        f"Append a new line `{SPIKE_MARKER}` to {rel} in this worktree only. "
        "Do not commit. When finished, print ONLY a JSON object with keys: "
        "stopped_cleanly, changed_files, checks, evidence_summary, risks."
    )


def run_live_delegate_spike(
    *,
    work_parent: Path | None = None,
    cleanup: bool = True,
) -> dict[str, Any]:
    """Run delegate handoff attach against a disposable worktree execution."""
    from agent_lab.agents.cursor_agent import is_available as cursor_available
    from agent_lab.run.meta import patch_run_meta, read_run_meta, write_run_meta

    mode = _delegate_mode()
    report: dict[str, Any] = {
        "kind": "live_delegate_dry_run",
        "started_at": _now(),
        "status": "skipped",
        "mode": mode,
        "checks": {},
        "preflight": {},
        "execution": None,
        "delegate": None,
        "errors": [],
    }

    if os.getenv("AGENT_LAB_SKIP_LIVE", "").strip().lower() in {"1", "true", "yes"}:
        report["errors"].append("AGENT_LAB_SKIP_LIVE set")
        report["finished_at"] = _now()
        return report

    if mode == "codex":
        preflight = _preflight_codex()
        report["preflight"] = preflight
        if not preflight.get("available"):
            report["errors"].append("Codex CLI unavailable (CODEX_BIN)")
            report["finished_at"] = _now()
            return report
    else:
        report["preflight"] = {"mode": "mock"}

    if not cursor_available():
        report["errors"].append("Cursor unavailable for worktree dry-run seed")
        report["finished_at"] = _now()
        return report

    parent = work_parent or Path(tempfile.mkdtemp(prefix="agent-lab-delegate-spike-"))
    owns_parent = work_parent is None
    repo = parent / "repo"
    session = parent / "session"
    session.mkdir(parents=True, exist_ok=True)
    write_run_meta(
        session,
        {
            "workflow_id": "room",
            "run_schema_version": 1,
            "topic": "live delegate spike",
            "created_at": _now(),
        },
    )

    tools_yaml = parent / "tools.yaml"
    tool_id = DELEGATE_TOOL_MOCK
    if mode == "mock":
        _mock_tools_yaml(tools_yaml)
    else:
        tool_id = DELEGATE_TOOL_CODEX

    try:
        _init_spike_repo(repo)
        plan_md = _plan_md(repo)
        (session / "plan.md").write_text(plan_md, encoding="utf-8")
        _seed_plan_snapshot(session, plan_md)

        permissions = {"_discuss_cwd": str(repo.resolve())}
        os.environ["AGENT_LAB_EXECUTE_INBOX"] = "0"
        os.environ["AGENT_LAB_EXTERNAL_TOOLS"] = "1"

        with patch(
            "agent_lab.agents.cursor_agent.respond",
            return_value="delegate spike: cursor dry-run noop",
        ):
            execution = run_dry_run(
                session,
                action_index=1,
                permissions=permissions,
            )

        report["execution"] = {
            "id": execution.get("id"),
            "status": execution.get("status"),
            "worktree_path": execution.get("worktree_path"),
            "isolation_effective": execution.get("isolation_effective"),
        }

        patch_run_meta(
            session,
            lambda run: patch_external_tools_allowlist(run, [tool_id]),
        )

        tools_patch = (
            patch("agent_lab.external_tools._tools_paths", return_value=[tools_yaml])
            if mode == "mock"
            else nullcontext()
        )
        delegate_args = _delegate_prompt() if mode == "codex" else SPIKE_MARKER
        with tools_patch:
            delegate_result = run_external_command(
                session,
                tool_id,
                args=delegate_args,
                confirm=True,
            )

        report["delegate"] = {
            "tool_id": tool_id,
            "ok": delegate_result.get("ok"),
            "status": delegate_result.get("status"),
            "exit_code": delegate_result.get("exit_code"),
            "handoff_attach": delegate_result.get("handoff_attach"),
            "stderr_tail": str(delegate_result.get("stderr") or "")[-500:],
        }

        run = read_run_meta(session)
        pending = next(
            (
                row
                for row in reversed(run.get("executions") or [])
                if isinstance(row, dict) and row.get("id") == execution.get("id")
            ),
            None,
        )
        handoff = public_external_handoff(pending if isinstance(pending, dict) else None)
        worktree_path = Path(str(execution.get("worktree_path") or ""))
        worktree_text = (
            worktree_path.joinpath(SPIKE_REL_PATH).read_text(encoding="utf-8") if worktree_path.is_dir() else ""
        )
        main_text = (repo / SPIKE_REL_PATH).read_text(encoding="utf-8")

        checks = {
            "pending_approval": execution.get("status") == "pending_approval",
            "worktree_exists": worktree_path.is_dir(),
            "delegate_ok": bool(delegate_result.get("ok")),
            "handoff_attached": bool(handoff and handoff.get("evidence_summary")),
            "marker_in_worktree": SPIKE_MARKER in worktree_text,
            "marker_not_on_main": SPIKE_MARKER not in main_text,
            "main_clean_after_delegate": _git_porcelain(repo) == "",
        }
        report["checks"] = checks
        if handoff:
            report["handoff"] = {
                "evidence_summary": handoff.get("evidence_summary"),
                "tool_id": handoff.get("tool_id"),
                "source": handoff.get("source"),
            }

        if execution.get("status") == "pending_approval" and execution.get("id"):
            resolve_execution(
                session,
                execution_id=str(execution["id"]),
                vote="reject",
                permissions=permissions,
            )
            checks["worktree_removed_after_reject"] = not worktree_path.exists()

        failed = [name for name, ok in checks.items() if not ok]
        report["status"] = "go" if not failed else "no_go"
        if failed:
            report["errors"].append(f"failed checks: {', '.join(failed)}")
    except Exception as exc:  # noqa: BLE001
        report["status"] = "no_go"
        report["errors"].append(str(exc))
    finally:
        report["finished_at"] = _now()
        if cleanup and owns_parent and parent.exists():
            shutil.rmtree(parent, ignore_errors=True)

    return report


def format_report_lines(report: dict[str, Any]) -> list[str]:
    lines = [
        f"Live delegate dry-run ({report.get('mode')}): {report.get('status', 'unknown').upper()}",
    ]
    if report.get("preflight"):
        lines.append(f"  preflight: {report['preflight']}")
    for key, ok in sorted((report.get("checks") or {}).items()):
        lines.append(f"  {key}: {'OK' if ok else 'FAIL'}")
    if report.get("handoff"):
        lines.append(f"  handoff: {report['handoff'].get('evidence_summary')}")
    for err in report.get("errors") or []:
        lines.append(f"  error: {err}")
    return lines
