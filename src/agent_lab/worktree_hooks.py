"""Optional repo `.agent-lab/worktree.yaml` lifecycle hooks (MB-6 + ABSORB P2)."""

from __future__ import annotations

import fnmatch
import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from agent_lab.subprocess_env import subprocess_env
from agent_lab.time_utils import utc_now_iso as _now_iso

_WORKTREE_HOOK_FILENAMES = ("worktree.yaml", "worktree.json")
_LIST_KEYS = frozenset({"setup", "verify", "create", "remove", "include"})
_MAX_INCLUDE_COPIES = 200


@dataclass(frozen=True)
class WorktreeHooksConfig:
    setup: tuple[str, ...] = ()
    verify: tuple[str, ...] = ()
    create: tuple[str, ...] = ()
    remove: tuple[str, ...] = ()
    include: tuple[str, ...] = ()
    base_ref: str | None = None
    source_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "setup": list(self.setup),
            "verify": list(self.verify),
            "create": list(self.create),
            "remove": list(self.remove),
            "include": list(self.include),
            "baseRef": self.base_ref,
            "source_path": self.source_path,
        }

    @property
    def has_any(self) -> bool:
        return bool(self.setup or self.verify or self.create or self.remove or self.include or self.base_ref)


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
        list_header = line[:-1] if line.endswith(":") and not line.startswith("-") else None
        if list_header in _LIST_KEYS and " " not in list_header:
            current_list = list_header
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


def _normalize_base_ref(raw: dict[str, Any]) -> str | None:
    for key in ("baseRef", "base_ref", "baseref"):
        val = raw.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return None


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
    config = WorktreeHooksConfig(
        setup=tuple(_parse_command_list(raw.get("setup"))),
        verify=tuple(_parse_command_list(raw.get("verify"))),
        create=tuple(_parse_command_list(raw.get("create"))),
        remove=tuple(_parse_command_list(raw.get("remove"))),
        include=tuple(_parse_command_list(raw.get("include"))),
        base_ref=_normalize_base_ref(raw),
        source_path=str(path),
    )
    if not config.has_any:
        return None
    return config


def find_worktree_hooks(git_root: Path | None) -> WorktreeHooksConfig | None:
    if git_root is None:
        return None
    root = git_root.resolve()
    for name in _WORKTREE_HOOK_FILENAMES:
        repo_path = root / ".agent-lab" / name
        if repo_path.is_file():
            return _load_hooks_file(repo_path)
    return None


def resolve_worktree_base_ref(git_root: Path | None) -> str | None:
    """Return configured baseRef when the git ref resolves; else None."""
    config = find_worktree_hooks(git_root)
    if not config or not config.base_ref or git_root is None:
        return None
    root = git_root.resolve()
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--verify", config.base_ref],
            capture_output=True,
            text=True,
            check=False,
            env=subprocess_env(),
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    return config.base_ref


def resolve_include_patterns(
    git_root: Path | None,
    config: WorktreeHooksConfig | None = None,
) -> list[str]:
    """Resolve include globs from yaml, or fall back to repo-root `.worktreeinclude`."""
    cfg = config if config is not None else find_worktree_hooks(git_root)
    patterns: list[str] = []
    if cfg and cfg.include:
        for item in cfg.include:
            if item in {"@.worktreeinclude", ".worktreeinclude"}:
                patterns.extend(_read_worktreeinclude(git_root))
            else:
                patterns.append(item)
    elif git_root is not None:
        patterns.extend(_read_worktreeinclude(git_root))
    # de-dupe preserve order
    seen: set[str] = set()
    out: list[str] = []
    for p in patterns:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def _read_worktreeinclude(git_root: Path | None) -> list[str]:
    if git_root is None:
        return []
    path = git_root.resolve() / ".worktreeinclude"
    if not path.is_file():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out: list[str] = []
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        out.append(line)
    return out


def apply_worktree_include(
    *,
    git_root: Path,
    worktree_path: Path,
    patterns: list[str] | None = None,
) -> dict[str, Any]:
    """Copy matching paths from git_root into the worktree (Codex .worktreeinclude).

    Git worktree already has tracked files; this copies extra local paths
    (env, secrets, build artifacts) listed by include patterns.
    """
    root = git_root.resolve()
    dest_root = worktree_path.resolve()
    pats = patterns if patterns is not None else resolve_include_patterns(root)
    copied: list[str] = []
    skipped: list[str] = []
    if not pats:
        return {
            "ok": True,
            "phase": "include",
            "patterns": [],
            "copied": [],
            "skipped": [],
            "ran_at": _now_iso(),
        }

    candidates: list[Path] = []
    for pat in pats:
        # Absolute-ish or rooted patterns relative to git root
        if any(ch in pat for ch in "*?["):
            for path in root.rglob("*"):
                if not path.is_file():
                    continue
                try:
                    rel = path.relative_to(root).as_posix()
                except ValueError:
                    continue
                if fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch(path.name, pat):
                    candidates.append(path)
        else:
            candidate = (root / pat).resolve()
            if candidate.is_file():
                candidates.append(candidate)
            elif candidate.is_dir():
                for path in candidate.rglob("*"):
                    if path.is_file():
                        candidates.append(path)

    for src in candidates:
        if len(copied) >= _MAX_INCLUDE_COPIES:
            skipped.append(str(src))
            continue
        try:
            rel = src.resolve().relative_to(root)
        except ValueError:
            skipped.append(str(src))
            continue
        dest = dest_root / rel
        if dest.exists():
            skipped.append(rel.as_posix())
            continue
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            copied.append(rel.as_posix())
        except OSError:
            skipped.append(rel.as_posix())

    return {
        "ok": True,
        "phase": "include",
        "patterns": pats,
        "copied": copied,
        "skipped": skipped[:50],
        "ran_at": _now_iso(),
    }


def public_config_summary(
    git_root: Path | None,
    *,
    include_report: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    config = find_worktree_hooks(git_root)
    patterns = resolve_include_patterns(git_root, config)
    if config is None and not patterns:
        return None
    return {
        "baseRef": config.base_ref if config else None,
        "include": patterns,
        "include_copied": list(include_report.get("copied") or []) if isinstance(include_report, dict) else [],
        "has_create": bool(config.create) if config else False,
        "has_remove": bool(config.remove) if config else False,
        "has_setup": bool(config.setup) if config else False,
        "has_verify": bool(config.verify) if config else False,
        "source_path": config.source_path if config else None,
    }


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


def _run_configured_phase(
    *,
    worktree_path: Path,
    git_root: Path,
    phase: Literal["create", "setup", "verify"],
) -> dict[str, Any] | None:
    config = find_worktree_hooks(git_root)
    if not config:
        return None
    commands = getattr(config, phase)
    if not commands:
        return None
    report = run_hook_commands(commands, cwd=worktree_path, phase=phase)
    report["config"] = config.to_dict()
    return report


def run_worktree_create(
    *,
    worktree_path: Path,
    git_root: Path,
) -> dict[str, Any] | None:
    return _run_configured_phase(
        worktree_path=worktree_path,
        git_root=git_root,
        phase="create",
    )


def run_worktree_setup(
    *,
    worktree_path: Path,
    git_root: Path,
) -> dict[str, Any] | None:
    return _run_configured_phase(
        worktree_path=worktree_path,
        git_root=git_root,
        phase="setup",
    )


def run_worktree_verify(
    *,
    worktree_path: Path,
    git_root: Path,
) -> dict[str, Any] | None:
    return _run_configured_phase(
        worktree_path=worktree_path,
        git_root=git_root,
        phase="verify",
    )


def run_worktree_remove(
    *,
    worktree_path: Path,
    git_root: Path,
) -> dict[str, Any] | None:
    """Best-effort remove hooks before worktree teardown."""
    config = find_worktree_hooks(git_root)
    if not config or not config.remove:
        return None
    if not worktree_path.is_dir():
        return {
            "phase": "remove",
            "ok": True,
            "skipped": True,
            "detail": "worktree path missing",
            "ran_at": _now_iso(),
            "config": config.to_dict(),
        }
    report = run_hook_commands(config.remove, cwd=worktree_path, phase="remove")
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
    create = block.get("create") if isinstance(block.get("create"), dict) else None
    remove = block.get("remove") if isinstance(block.get("remove"), dict) else None
    return {
        "setup_ok": None if setup is None else bool(setup.get("ok")),
        "verify_ok": None if verify is None else bool(verify.get("ok")),
        "create_ok": None if create is None else bool(create.get("ok")),
        "remove_ok": None if remove is None else bool(remove.get("ok")),
        "setup": setup,
        "verify": verify,
        "create": create,
        "remove": remove,
        "config_summary": block.get("config_summary"),
    }
