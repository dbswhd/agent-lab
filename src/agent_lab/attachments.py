"""Session file attachments — store and summarize for agent prompts."""

from __future__ import annotations

from pathlib import Path

TEXT_SUFFIXES = {
    ".txt",
    ".md",
    ".markdown",
    ".json",
    ".jsonl",
    ".csv",
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".html",
    ".diff",
    ".patch",
    ".css",
    ".yaml",
    ".yml",
    ".xml",
    ".env",
    ".log",
    ".rst",
}
MAX_TEXT_CHARS = 24_000
MAX_FILES = 20
MAX_FILE_BYTES = 8 * 1024 * 1024


def attachments_dir(session_folder: Path) -> Path:
    d = session_folder / "attachments"
    d.mkdir(parents=True, exist_ok=True)
    return d


def list_attachment_names(session_folder: Path) -> list[str]:
    d = session_folder / "attachments"
    if not d.is_dir():
        return []
    return sorted(f.name for f in d.iterdir() if f.is_file())


def describe_attachments(session_folder: Path) -> str:
    """Build a prompt appendix from files in session attachments/."""
    d = session_folder / "attachments"
    if not d.is_dir():
        return ""
    parts: list[str] = []
    for f in sorted(d.iterdir()):
        if not f.is_file():
            continue
        suffix = f.suffix.lower()
        size = f.stat().st_size
        if size > MAX_FILE_BYTES:
            parts.append(f"### {f.name}\n(binary, {size} bytes — too large to inline)")
            continue
        if suffix in TEXT_SUFFIXES:
            try:
                text = f.read_text(encoding="utf-8", errors="replace")
            except OSError as e:
                parts.append(f"### {f.name}\n(read error: {e})")
                continue
            if len(text) > MAX_TEXT_CHARS:
                text = text[:MAX_TEXT_CHARS] + "\n…(truncated)"
            parts.append(f"### {f.name}\n```\n{text}\n```")
        else:
            parts.append(f"- **{f.name}** ({size} bytes, type `{suffix or 'unknown'}`)")
    if not parts:
        return ""
    return "Attached files:\n\n" + "\n\n".join(parts)
