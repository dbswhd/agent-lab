"""Optional repo `.agent-lab/worktree.yaml` setup/verify hooks (MB-6)."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_lab.subprocess_env import subprocess_env

_WORKTREE_HOOK_FILENAMES = ("worktree.yaml", "worktree.json")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class WorktreeHooksConfig:
    setup: tuple[str, ...]
    verify: tuple[str, ...]
    source_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "setup": list(self.setup),
            "verify": list(self.verify),
            "source_path": self.source_path,
        }


def _parse_command_list(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    return [str(item).strip() for item in raw if str(item).strip()]


def _parse_yaml_hooks(text: str) -> dict[str, Any]:
    data: dict[str, Any] = {}
    current_list: str | None = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line in {"setup:", "verify:"}:
            current_list = line[:-1]
            data.setdefault(current_list, [])
            continue
        if line.startswith("- ") and current_list:
            items = data.setdefault(current_list, [])
            if isinstance(items, list):
                items.append(line[2:].strip().strip('"').strip("'"))
            continue
        if ":" in line:
            key, value = line.split(":", 1)
            data[key.strip()] = value.strip().strip('"').strip("'")
            current_list = None
    return data


def _load_hooks_file(path: Path) -> WorktreeHooksConfig | None:
    try:
        if path.suffix == ".json":
            raw = json.loads(path.read_text(encoding="utf-8"))
        else:
            raw = _parse_yaml_hooks(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    if not isinstance(raw, dict):
        return None
    setup = _parse_command_list(raw.get("setup"))
    verify = _parse_command_list(raw.get("verify"))
    if not setup and not verify:
        return None
    return WorktreeHooksConfig(
        setup=tuple(setup),
        verify=tuple(verify),
        source_path=str(path),
    )


def find_worktree_hooks(git_root: Path | None) -> WorktreeHooksConfig | None:
    if git_root is None:
        return None
    root = git_root.resolve()
    for name in _WORKTREE_HOOK_FILENAMES:
        repo_path = root / ".agent-lab" / name
        if repo_path.is_file():
            return _load_hooks_file(repo_path)
    return None


def _sandbox_intent() -> str | None:
    """Resolve the sandbox runtime intent for this verify subprocess.

    Returns None when AGENT_LAB_SANDBOX_POLICY is off (OFF-parity: no key added to
    the result dict). When on with runtime="docker", live Docker is DEFERRED, so we
    return "docker" as an intent marker while the caller still runs the worktree
    subprocess (fallback). runtime="worktree" returns None (no marker needed).
    """
    from agent_lab.sandbox_policy import resolve_sandbox_policy, sandbox_policy_enabled

    if not sandbox_policy_enabled():
        return None
    policy = resolve_sandbox_policy()
    return "docker" if policy.get("runtime") == "docker" else None


def _run_command(cmd: str, *, cwd: Path, timeout_sec: float = 600.0) -> dict[str, Any]:
    intent = _sandbox_intent()

    def _finish(row: dict[str, Any]) -> dict[str, Any]:
        if intent is not None:
            row["sandbox_intent"] = intent
        return row

    try:
        result = subprocess.run(
            cmd,
            shell=True,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            env=subprocess_env(),
        )
    except subprocess.TimeoutExpired:
        return _finish(
            {
                "cmd": cmd,
                "exit": -1,
                "ok": False,
                "detail": f"timeout after {int(timeout_sec)}s",
                "stdout": "",
                "stderr": "",
            }
        )
    except OSError as exc:
        return _finish(
            {
                "cmd": cmd,
                "exit": -1,
                "ok": False,
                "detail": str(exc)[:200],
                "stdout": "",
                "stderr": "",
            }
        )
    stdout = (result.stdout or "")[:2000]
    stderr = (result.stderr or "")[:2000]
    ok = result.returncode == 0
    return _finish(
        {
            "cmd": cmd,
            "exit": int(result.returncode),
            "ok": ok,
            "detail": None if ok else (stderr.strip() or stdout.strip() or f"exit {result.returncode}"),
            "stdout": stdout,
            "stderr": stderr,
        }
    )


def run_hook_commands(
    commands: tuple[str, ...] | list[str],
    *,
    cwd: Path,
    phase: str,
) -> dict[str, Any]:
    rows = [_run_command(str(cmd), cwd=cwd) for cmd in commands if str(cmd).strip()]
    ok = all(row.get("ok") for row in rows) if rows else True
    return {
        "phase": phase,
        "ok": ok,
        "ran_at": _now_iso(),
        "results": rows,
    }


def run_worktree_setup(
    *,
    worktree_path: Path,
    git_root: Path,
) -> dict[str, Any] | None:
    config = find_worktree_hooks(git_root)
    if not config or not config.setup:
        return None
    report = run_hook_commands(config.setup, cwd=worktree_path, phase="setup")
    report["config"] = config.to_dict()
    return report


def run_worktree_verify(
    *,
    worktree_path: Path,
    git_root: Path,
) -> dict[str, Any] | None:
    config = find_worktree_hooks(git_root)
    if not config or not config.verify:
        return None
    report = run_hook_commands(config.verify, cwd=worktree_path, phase="verify")
    report["config"] = config.to_dict()
    return report


def public_worktree_hooks_status(execution: dict[str, Any] | None) -> dict[str, Any] | None:
    if not execution:
        return None
    block = execution.get("worktree_hooks")
    if not isinstance(block, dict):
        return None
    setup = block.get("setup") if isinstance(block.get("setup"), dict) else None
    verify = block.get("verify") if isinstance(block.get("verify"), dict) else None
    return {
        "setup_ok": None if setup is None else bool(setup.get("ok")),
        "verify_ok": None if verify is None else bool(verify.get("ok")),
        "setup": setup,
        "verify": verify,
    }
