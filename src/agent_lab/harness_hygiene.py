from __future__ import annotations

import re
from pathlib import Path
from typing import TypedDict
from urllib.parse import urlparse

from agent_lab.run.profile import feature_flags_without_owner
from agent_lab.trace_episode import TRACE_SCHEMA_VERSION

_AUTHORITATIVE_DOCS = (
    "AGENTS.md",
    ".agent-lab/PROJECT.md",
    "docs/ARCHITECTURE.md",
    "docs/TURN-CONTRACT.md",
    "docs/TURN-POLICY.md",
    "docs/EXTERNAL-REFS-TRACEABILITY.md",
)
_MARKDOWN_LINK = re.compile(r"\]\(([^)]+)\)")


class DocsHygiene(TypedDict):
    checked_sources: list[str]
    missing_sources: list[str]
    broken_links: list[str]


class HarnessHygieneReport(TypedDict):
    ok: bool
    docs: DocsHygiene
    flags: dict[str, list[str]]
    trace: dict[str, int]


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _local_link_target(source: Path, raw: str) -> Path | None:
    target = raw.strip().split(" ", 1)[0].strip("<>")
    parsed = urlparse(target)
    if parsed.scheme or parsed.netloc or target.startswith("#") or target.startswith("/"):
        return None
    path = parsed.path.split("#", 1)[0]
    if not path:
        return None
    return (source.parent / path).resolve()


def _broken_links(root: Path, source: Path) -> list[str]:
    broken: list[str] = []
    for raw in _MARKDOWN_LINK.findall(source.read_text(encoding="utf-8")):
        target = _local_link_target(source, raw)
        if target is not None and not target.exists():
            broken.append(f"{source.relative_to(root)} -> {raw.strip()}")
    return broken


def build_harness_hygiene_report(root: Path | None = None) -> HarnessHygieneReport:
    base = (root or project_root()).resolve()
    missing_sources: list[str] = []
    broken_links: list[str] = []
    checked_sources: list[str] = []
    for relative in _AUTHORITATIVE_DOCS:
        source = base / relative
        if not source.is_file():
            missing_sources.append(relative)
            continue
        checked_sources.append(relative)
        broken_links.extend(_broken_links(base, source))
    unowned_flags = feature_flags_without_owner()
    return {
        "ok": not missing_sources and not broken_links and not unowned_flags,
        "docs": {
            "checked_sources": checked_sources,
            "missing_sources": missing_sources,
            "broken_links": broken_links,
        },
        "flags": {"unowned_feature_flags": unowned_flags},
        "trace": {"trace_schema_version": TRACE_SCHEMA_VERSION},
    }
