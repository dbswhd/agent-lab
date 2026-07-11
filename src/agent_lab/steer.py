"""Mid-run Human steer queue (ABSORB P1) — informational only, no gate bypass."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

from agent_lab.time_utils import utc_now_iso_z as _now_iso
from agent_lab.run.meta import patch_run_meta, read_run_meta, stamp_run_meta
from agent_lab.run.state import RunStateLike

_MAX_STEER_TEXT = 2000
_MAX_QUEUE = 20



def folder_from_run_meta(run_meta: RunStateLike | None) -> Path | None:
    if not isinstance(run_meta, dict):
        return None
    raw = run_meta.get("_session_folder")
    if isinstance(raw, str) and raw.strip():
        path = Path(raw).expanduser()
        if path.is_dir():
            return path
    sid = str(run_meta.get("_session_id") or run_meta.get("session_id") or "").strip()
    if not sid:
        return None
    # Prefer exact folder name under active sessions (id == folder.name).
    try:
        from agent_lab.session.paths import active_sessions_dir

        root = active_sessions_dir()
        if root.is_dir():
            for child in root.iterdir():
                if child.is_dir() and child.name == sid:
                    return child
            # Nested day folders
            for day in root.iterdir():
                if not day.is_dir():
                    continue
                candidate = day / sid
                if candidate.is_dir():
                    return candidate
    except Exception:
        pass
    return None


def list_steer_queue(run_meta: RunStateLike | None) -> list[dict[str, Any]]:
    if not isinstance(run_meta, dict):
        return []
    raw = run_meta.get("steer_queue")
    if not isinstance(raw, list):
        return []
    return [row for row in raw if isinstance(row, dict) and str(row.get("text") or "").strip()]


def enqueue_steer(folder: Path, text: str, *, target: str = "any") -> dict[str, Any]:
    """Queue a Human steer note. Does not approve plan/execute or resolve Inbox."""
    cleaned = (text or "").strip()
    if not cleaned:
        raise ValueError("steer text required")
    if len(cleaned) > _MAX_STEER_TEXT:
        cleaned = cleaned[:_MAX_STEER_TEXT].rstrip() + "…"
    tgt = target if target in {"room", "execute", "any"} else "any"
    entry = {
        "id": f"steer_{uuid4().hex[:10]}",
        "text": cleaned,
        "ts": _now_iso(),
        "target": tgt,
    }

    def _patch(run: dict[str, Any]) -> dict[str, Any]:
        queue = list_steer_queue(run)
        queue.append(entry)
        run["steer_queue"] = queue[-_MAX_QUEUE:]
        return run

    patch_run_meta(folder, _patch)
    try:
        from agent_lab.mission.notepad import append_wisdom_note

        append_wisdom_note(folder, line=f"[steer] {cleaned}", filename="learnings.md")
    except Exception:
        pass
    meta = read_run_meta(folder)
    return {
        "ok": True,
        "entry": entry,
        "queued": len(list_steer_queue(meta)),
    }


def drain_steer_follow_up(
    folder: Path | None = None,
    run_meta: RunStateLike | None = None,
    *,
    target: str = "any",
) -> str:
    """Pop queued steers into a follow-up block for the next agent invoke."""
    path = folder or folder_from_run_meta(run_meta)
    drained: list[str] = []

    def _take(queue: list[dict[str, Any]]) -> list[dict[str, Any]]:
        nonlocal drained
        keep: list[dict[str, Any]] = []
        for row in queue:
            row_target = str(row.get("target") or "any")
            if target != "any" and row_target not in {target, "any"}:
                keep.append(row)
                continue
            text = str(row.get("text") or "").strip()
            if text:
                drained.append(text)
        return keep

    if path is not None and path.is_dir():

        def _patch(run: dict[str, Any]) -> dict[str, Any]:
            run["steer_queue"] = _take(list_steer_queue(run))
            return run

        patch_run_meta(path, _patch)
    elif isinstance(run_meta, dict):
        stamp_run_meta(run_meta, steer_queue=_take(list_steer_queue(run_meta)))
    else:
        return ""

    if not drained:
        return ""
    lines = "\n".join(f"- {t}" for t in drained)
    return f"[Human steer — apply before continuing]\n{lines}"


def peek_steer_count(folder: Path) -> int:
    return len(list_steer_queue(read_run_meta(folder)))
