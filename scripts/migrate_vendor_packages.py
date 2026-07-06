#!/usr/bin/env python3
"""One-shot: move cursor/codex/claude modules into vendor packages and rewrite imports."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "agent_lab"

# Order matters — longer / more specific patterns first.
IMPORT_REWRITES = (
    (re.compile(r"\bagent_lab\.cursor_inbox_mcp\b"), "agent_lab.cursor.inbox_mcp"),
    (re.compile(r"\bagent_lab\.cursor_bridge\b"), "agent_lab.cursor.bridge"),
    (re.compile(r"\bagent_lab\.cursor_activity\b"), "agent_lab.cursor.activity"),
    (re.compile(r"\bagent_lab\.bridge_registry\b"), "agent_lab.cursor.registry"),
    (re.compile(r"\bagent_lab\.codex_oauth\b"), "agent_lab.codex.oauth"),
    (re.compile(r"\bagent_lab\.codex_cli\b"), "agent_lab.codex.cli"),
    (re.compile(r"\bagent_lab\.claude_cli\b"), "agent_lab.claude.cli"),
    (
        re.compile(r"\bfrom agent_lab import claude_cli, codex_cli\b"),
        "from agent_lab.claude import cli as claude_cli\nfrom agent_lab.codex import cli as codex_cli",
    ),
    (
        re.compile(r"\bfrom agent_lab import codex_cli, claude_cli\b"),
        "from agent_lab.codex import cli as codex_cli\nfrom agent_lab.claude import cli as claude_cli",
    ),
    (re.compile(r"\bimport agent_lab\.codex_cli\b"), "import agent_lab.codex.cli as codex_cli"),
    (re.compile(r"\bimport agent_lab\.claude_cli\b"), "import agent_lab.claude.cli as claude_cli"),
)

SCAN_ROOTS = (
    SRC,
    ROOT / "app",
    ROOT / "tests",
    ROOT / "scripts",
)

CURSOR_MOVES: tuple[tuple[str, str], ...] = (
    ("cursor_bridge.py", "bridge.py"),
    ("cursor_activity.py", "activity.py"),
    ("cursor_inbox_mcp.py", "inbox_mcp.py"),
    ("bridge_registry.py", "registry.py"),
)

CODEX_MOVES: tuple[tuple[str, str], ...] = (
    ("codex_cli.py", "cli.py"),
    ("codex_oauth.py", "oauth.py"),
)

CLAUDE_MOVES: tuple[tuple[str, str], ...] = (("claude_cli.py", "cli.py"),)

AGENT_PROVIDER_MOVES: tuple[tuple[str, str, str], ...] = (
    ("agents/cursor_agent.py", "cursor", "provider.py"),
    ("agents/codex_agent.py", "codex", "provider.py"),
    ("agents/claude_agent.py", "claude", "provider.py"),
)


def _rewrite_imports(text: str) -> str:
    for pattern, repl in IMPORT_REWRITES:
        text = pattern.sub(repl, text)
    return text


def _ensure_init(pkg_dir: Path, doc: str) -> None:
    init = pkg_dir / "__init__.py"
    if not init.is_file():
        init.write_text(f'"""{doc}"""\n\nfrom __future__ import annotations\n', encoding="utf-8")


def _move_pair(src_name: str, dst_name: str, pkg_dir: Path) -> None:
    src = SRC / src_name
    if not src.is_file():
        return
    pkg_dir.mkdir(exist_ok=True)
    dst = pkg_dir / dst_name
    content = _rewrite_imports(src.read_text(encoding="utf-8"))
    dst.write_text(content, encoding="utf-8")
    src.unlink()


def move_modules() -> list[str]:
    moved: list[str] = []
    cursor_dir = SRC / "cursor"
    codex_dir = SRC / "codex"
    claude_dir = SRC / "claude"

    for src_name, dst_name in CURSOR_MOVES:
        if (SRC / src_name).is_file():
            _move_pair(src_name, dst_name, cursor_dir)
            moved.append(f"cursor/{dst_name}")

    for src_name, dst_name in CODEX_MOVES:
        if (SRC / src_name).is_file():
            _move_pair(src_name, dst_name, codex_dir)
            moved.append(f"codex/{dst_name}")

    for src_name, dst_name in CLAUDE_MOVES:
        if (SRC / src_name).is_file():
            _move_pair(src_name, dst_name, claude_dir)
            moved.append(f"claude/{dst_name}")

    for src_rel, pkg, dst_name in AGENT_PROVIDER_MOVES:
        src = SRC / src_rel
        if not src.is_file():
            continue
        pkg_dir = SRC / pkg
        pkg_dir.mkdir(exist_ok=True)
        dst = pkg_dir / dst_name
        content = _rewrite_imports(src.read_text(encoding="utf-8"))
        dst.write_text(content, encoding="utf-8")
        src.unlink()
        moved.append(f"{pkg}/{dst_name}")

    _ensure_init(cursor_dir, "Cursor SDK bridge, inbox MCP, and room provider.")
    _ensure_init(codex_dir, "Codex CLI adapter and OAuth profile management.")
    _ensure_init(claude_dir, "Claude CLI adapter and room provider.")
    return moved


def write_agent_shims() -> None:
    shims = {
        "cursor_agent.py": "agent_lab.cursor.provider",
        "codex_agent.py": "agent_lab.codex.provider",
        "claude_agent.py": "agent_lab.claude.provider",
    }
    agents_dir = SRC / "agents"
    for name, module in shims.items():
        path = agents_dir / name
        path.write_text(
            f'"""Backward-compatible shim — prefer ``{module}``."""\n\n'
            f"from __future__ import annotations\n\n"
            f"from {module} import *  # noqa: F403\n",
            encoding="utf-8",
        )


def rewrite_repo_imports() -> int:
    changed = 0
    vendor_dirs = {SRC / "cursor", SRC / "codex", SRC / "claude"}
    for base in SCAN_ROOTS:
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.py")):
            if any(path.is_relative_to(d) for d in vendor_dirs if d.is_dir()):
                continue
            if path.name.startswith("migrate_") and "package" in path.name:
                continue
            text = path.read_text(encoding="utf-8")
            new_text = _rewrite_imports(text)
            if new_text != text:
                path.write_text(new_text, encoding="utf-8")
                changed += 1
    # Rewrite imports inside vendor packages too.
    for pkg_dir in vendor_dirs:
        if not pkg_dir.is_dir():
            continue
        for path in sorted(pkg_dir.rglob("*.py")):
            text = path.read_text(encoding="utf-8")
            new_text = _rewrite_imports(text)
            if new_text != text:
                path.write_text(new_text, encoding="utf-8")
                changed += 1
    return changed


def main() -> None:
    moved = move_modules()
    write_agent_shims()
    print(f"Moved {len(moved)} modules into vendor packages:")
    for item in moved:
        print(f"  {item}")
    n = rewrite_repo_imports()
    print(f"Rewrote imports in {n} files")


if __name__ == "__main__":
    main()
