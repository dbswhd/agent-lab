from __future__ import annotations

import importlib.util
import json
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = _ROOT / "scripts" / "check_worktree_orphans.py"


def _load_guard():
    spec = importlib.util.spec_from_file_location("check_worktree_orphans", _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_orphan_guard_flags_orphan_and_terminal_but_keeps_pending(tmp_path: Path):
    guard = _load_guard()
    sessions = tmp_path / "sessions"
    folder = sessions / "sess"
    pending = folder / "worktrees" / "exec-pending"
    merged = folder / "worktrees" / "exec-merged"
    orphan = folder / "worktrees" / "exec-orphan"
    for path in (pending, merged, orphan):
        path.mkdir(parents=True)
    (folder / "run.json").write_text(
        json.dumps(
            {
                "executions": [
                    {
                        "id": "exec-pending",
                        "status": "pending_approval",
                        "worktree_path": str(pending),
                    },
                    {
                        "id": "exec-merged",
                        "status": "merged",
                        "worktree_path": str(merged),
                    },
                ]
            }
        )
        + "\n",
        encoding="utf-8",
    )

    stale = guard.find_stale_worktrees(sessions)

    assert any("exec-merged" in row for row in stale)
    assert any("exec-orphan" in row for row in stale)
    assert not any("exec-pending" in row for row in stale)
