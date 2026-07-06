"""Mission notepad files and mission-wisdom context block (Layer 6 Phase 5)."""

from __future__ import annotations

from agent_lab.run.state import RunStateLike
from pathlib import Path
from typing import Any

from agent_lab.run.meta import patch_run_meta, read_run_meta


MISSION_NOTEPAD_FILES: tuple[str, ...] = (
    "learnings.md",
    "verification.md",
    "decisions.md",
)


_NOTEPAD_HEADERS: dict[str, str] = {
    "learnings.md": "# Mission learnings\n\n",
    "verification.md": "# Mission verification log\n\n",
    "decisions.md": "# Mission decisions\n\n",
}


_NOTEPAD_READ_ORDER = ("verification.md", "learnings.md", "decisions.md")


MISSION_WISDOM_INJECT_CAP = 1500


_WISDOM_SKIP_PHASES = frozenset({"MISSION_DEFINE", "MISSION_DONE", "MISSION_PAUSED"})


def mission_notepad_dir(folder: Path) -> Path:
    return Path.home() / ".agent-lab" / "missions" / folder.name


def mission_notepad_rel(session_id: str, filename: str) -> str:
    return f"missions/{session_id}/{filename}"


def ensure_mission_notepads(folder: Path) -> list[str]:
    """Create mission notepad files with headers (Phase 5)."""
    from agent_lab.mission.loop import get_mission_loop

    base = mission_notepad_dir(folder)
    base.mkdir(parents=True, exist_ok=True)
    created: list[str] = []
    for name in MISSION_NOTEPAD_FILES:
        path = base / name
        if path.is_file():
            continue
        path.write_text(_NOTEPAD_HEADERS.get(name, f"# {name}\n\n"), encoding="utf-8")
        created.append(name)

    if not created:
        return created

    def _refs(run: dict[str, Any]) -> dict[str, Any]:
        m = get_mission_loop(run)
        refs = list(m.get("wisdom_refs") or [])
        for name in MISSION_NOTEPAD_FILES:
            rel = mission_notepad_rel(folder.name, name)
            if rel not in refs:
                refs.append(rel)
        m["wisdom_refs"] = refs
        run["mission_loop"] = m
        return run

    patch_run_meta(folder, _refs)
    return created


def _chat_provenance_ref(folder: Path) -> str | None:
    path = folder / "chat.jsonl"
    if not path.is_file():
        return None
    try:
        line_count = sum(1 for _ in path.open(encoding="utf-8"))
    except OSError:
        return None
    if line_count < 1:
        return None
    return f"chat.jsonl#L{line_count}"


def _plan_provenance_ref(folder: Path, action_index: int | None = None) -> str | None:
    plan_path = folder / "plan.md"
    if not plan_path.is_file():
        return None
    try:
        lines = plan_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    if not lines:
        return None
    if action_index is not None:
        needle = f"{action_index}."
        for i, line in enumerate(lines, start=1):
            if line.strip().startswith(needle):
                return f"plan (ref: L{i})"
    return f"plan.md#L{len(lines)}"


def _format_provenance(
    folder: Path,
    *,
    action_index: int | None = None,
    extra: str | None = None,
) -> str | None:
    parts: list[str] = []
    if extra:
        parts.append(extra.strip())
    chat = _chat_provenance_ref(folder)
    if chat:
        parts.append(chat)
    plan = _plan_provenance_ref(folder, action_index)
    if plan:
        parts.append(plan)
    return " · ".join(parts) if parts else None


def _read_notepad_tail(path: Path, *, max_chars: int) -> str:
    if not path.is_file() or max_chars < 1:
        return ""
    try:
        body = path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""
    if not body:
        return ""
    if len(body) <= max_chars:
        return body
    return "…\n" + body[-max_chars:]


def list_mission_notepad_summaries(folder: Path) -> list[dict[str, Any]]:
    """Summaries for API / UI (line counts + tail preview)."""
    base = mission_notepad_dir(folder)
    out: list[dict[str, Any]] = []
    for name in MISSION_NOTEPAD_FILES:
        path = base / name
        if not path.is_file():
            out.append({"file": name, "lines": 0, "preview": ""})
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            out.append({"file": name, "lines": 0, "preview": ""})
            continue
        lines = [ln for ln in text.splitlines() if ln.strip()]
        preview = _read_notepad_tail(path, max_chars=160)
        out.append(
            {
                "file": name,
                "lines": len(lines),
                "preview": preview,
                "path": str(path),
            }
        )
    return out


def _notepad_base_from_run_meta(run_meta: RunStateLike | None) -> Path | None:
    from agent_lab.mission.loop import get_mission_loop

    session_id = str((run_meta or {}).get("_session_id") or "").strip()
    home = Path.home() / ".agent-lab"
    if session_id:
        return home / "missions" / session_id
    ml = get_mission_loop(run_meta)
    for ref in ml.get("wisdom_refs") or []:
        if isinstance(ref, str) and ref.startswith("missions/"):
            parts = ref.split("/")
            if len(parts) >= 2 and parts[1]:
                return home / "missions" / parts[1]
    return None


def build_mission_wisdom_block(
    run_meta: RunStateLike | None,
    *,
    max_chars: int = MISSION_WISDOM_INJECT_CAP,
) -> str:
    """Phase 5: inject mission notepad tails into agent context."""
    from agent_lab.mission.loop import get_mission_loop
    from agent_lab.context.layers import mission_wisdom_layer_enabled

    if not mission_wisdom_layer_enabled(run_meta):
        return ""
    ml = get_mission_loop(run_meta)
    if not ml.get("enabled"):
        return ""
    phase = str(ml.get("phase") or "")
    if phase in _WISDOM_SKIP_PHASES:
        return ""
    base = _notepad_base_from_run_meta(run_meta)
    if base is None:
        return ""
    per_file = max(120, max_chars // len(_NOTEPAD_READ_ORDER))
    chunks: list[str] = []
    used = 0
    for name in _NOTEPAD_READ_ORDER:
        path = base / name
        tail = _read_notepad_tail(path, max_chars=per_file)
        if not tail:
            continue
        room = per_file - (used % per_file) if used else per_file
        if len(tail) > room and room > 0:
            tail = tail[-room:]
        chunks.append(f"[{name}]\n{tail}")
        used += len(tail)
        if used >= max_chars:
            break
    if not chunks:
        return ""
    block = "[Mission wisdom]\n" + "\n\n".join(chunks)
    return block[:max_chars]


def append_wisdom_note(
    folder: Path,
    *,
    line: str,
    filename: str = "learnings.md",
    action_index: int | None = None,
    provenance: str | None = None,
    auto_provenance: bool = True,
) -> str:
    """Append one line to a mission notepad with optional provenance."""
    from agent_lab.mission.loop import _now_iso, get_mission_loop

    if filename not in MISSION_NOTEPAD_FILES:
        filename = "learnings.md"
    ensure_mission_notepads(folder)
    path = mission_notepad_dir(folder) / filename
    text = (line or "").strip()
    prov = provenance
    if auto_provenance and not prov:
        prov = _format_provenance(folder, action_index=action_index)
    if text:
        entry = f"- {_now_iso()} {text}"
        if prov:
            entry += f" ({prov})"
        with path.open("a", encoding="utf-8") as fh:
            fh.write(f"{entry}\n")

    def _ref(run: dict[str, Any]) -> dict[str, Any]:
        m = get_mission_loop(run)
        refs = list(m.get("wisdom_refs") or [])
        for name in MISSION_NOTEPAD_FILES:
            r = mission_notepad_rel(folder.name, name)
            if r not in refs:
                refs.append(r)
        m["wisdom_refs"] = refs
        run["mission_loop"] = m
        return run

    patch_run_meta(folder, _ref)
    try:
        from agent_lab.wisdom.index import build_wisdom_index, wisdom_index_enabled

        if wisdom_index_enabled(read_run_meta(folder)):
            build_wisdom_index(folder, force=True)
    except Exception:
        pass
    return str(path)


def inject_wisdom_into_prompt(
    user: str,
    run_meta: RunStateLike | None,
) -> str:
    """Append [Mission wisdom] block to an execute/repair user prompt."""
    wisdom = build_mission_wisdom_block(run_meta)
    if not wisdom.strip():
        return user
    return f"{user.rstrip()}\n\n{wisdom.strip()}"
