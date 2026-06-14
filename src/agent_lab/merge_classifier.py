"""Low-risk merge classifier (Gate 1-B)."""

from __future__ import annotations

from typing import Any, Literal

ClassifierKind = Literal["docs_only", "test_only", "single_file"]

_DENY_EXACT = frozenset(
    {
        "pyproject.toml",
        "setup.py",
        "setup.cfg",
        "Cargo.toml",
        "go.mod",
        "package.json",
        "package-lock.json",
    }
)

_DENY_PREFIXES = (
    ".github/",
    ".gitlab/",
    "migrations/",
    "alembic/",
)

_DOCS_PREFIXES = ("docs/", "doc/", "sessions/_regression/")
_DOCS_NAMES = frozenset({"readme.md", "changelog.md", "license", "license.md"})


def _norm_path(path: str) -> str:
    return path.replace("\\", "/").lstrip("./")


def _is_deny_path(path: str) -> bool:
    norm = _norm_path(path).lower()
    if norm in _DENY_EXACT:
        return True
    return any(norm.startswith(prefix) for prefix in _DENY_PREFIXES)


def _is_docs_path(path: str) -> bool:
    norm = _norm_path(path)
    lower = norm.lower()
    if lower.endswith(".md") or lower.endswith(".mdx"):
        return True
    if lower in _DOCS_NAMES:
        return True
    return any(lower.startswith(prefix) for prefix in _DOCS_PREFIXES)


def _is_test_path(path: str) -> bool:
    norm = _norm_path(path)
    return norm.startswith("tests/") or "/tests/" in norm


def classify_source_paths(source_paths: list[str]) -> ClassifierKind | None:
    """Return classifier kind, or None when auto-merge must not run."""
    paths = [_norm_path(p) for p in source_paths if str(p).strip()]
    if not paths:
        return None
    if any(_is_deny_path(p) for p in paths):
        return None
    if all(_is_docs_path(p) for p in paths):
        return "docs_only"
    if all(_is_test_path(p) for p in paths):
        return "test_only"
    non_test = [p for p in paths if not _is_test_path(p)]
    if len(non_test) <= 1:
        return "single_file"
    return None


def classify_execution(execution: dict[str, Any]) -> ClassifierKind | None:
    source = list(
        execution.get("source_touched_paths")
        or execution.get("touched_paths")
        or []
    )
    return classify_source_paths(source)


def public_classifier_preview(execution: dict[str, Any] | None) -> dict[str, Any]:
    if not execution:
        return {"classifier": None, "eligible_kind": None, "source_paths": []}
    source = list(
        execution.get("source_touched_paths")
        or execution.get("touched_paths")
        or []
    )
    kind = classify_source_paths(source)
    return {
        "classifier": kind,
        "eligible_kind": kind,
        "source_paths": source,
        "deny": kind is None and bool(source),
    }
