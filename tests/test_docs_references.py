"""Guard: the docs that claim to be SSOT must not point at files that moved.

``EXTERNAL-REFS-TRACEABILITY.md`` is named as the shipped-status SSOT by README,
CLAUDE.md and AGENTS.md. A row marked ✅ is only as good as the evidence path it
cites, and package refactors (``room.py`` -> ``room/``, ``plan_execute*.py`` ->
``plan/``) silently rot those paths while the ✅ stays put. A stale SSOT is worse
than none: it lends authority to a claim nobody can check.

The same applies to the headline counts in README — flags, regression baselines,
routers. They were each wrong by 2-3x before this guard existed.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

TRACEABILITY = ROOT / "docs" / "EXTERNAL-REFS-TRACEABILITY.md"
README = ROOT / "README.md"

# Anything that is not the live source tree: build output, vendored runtimes,
# throwaway worktrees, design mirrors. A reference that only resolves inside one
# of these is dead as far as the product is concerned.
EXCLUDED_PARTS = {
    ".venv",
    ".git",
    ".mypy_cache",
    ".ruff_cache",
    "__pycache__",
    ".omo",
    "node_modules",
    "sessions",
    "worktrees",
    "target",
    "bundled-runtime",
    "design-handoff",
    "scratch",
    "artifacts",
}
EXTS = (".py", ".ts", ".tsx", ".md", ".json", ".toml", ".yml", ".yaml")

# Referenced deliberately as something the repo does not contain: operator-authored
# runtime config (the repo ships only `.example` templates) and an external vault.
ALLOWED_MISSING = {
    "notes/05-agent-lab/gajae-code-workflow-pipeline.md",  # external notes vault
    ".agent-lab/worktree.yaml",  # operator config; repo has no template for it
    "tools.yaml",  # operator config; repo ships .agent-lab/tools.yaml.example
}


def _live_index() -> dict[str, list[str]]:
    index: dict[str, list[str]] = {}
    for path in ROOT.rglob("*"):
        if path.suffix not in EXTS or not path.is_file():
            continue
        if any(part in EXCLUDED_PARTS for part in path.parts):
            continue
        index.setdefault(path.name, []).append(str(path.relative_to(ROOT)))
    return index


def _resolve(token: str, index: dict[str, list[str]]) -> list[str]:
    tok = token.strip().lstrip("./")
    if not tok:
        return []
    if (ROOT / tok).exists():
        return [tok]
    doc_rel = (TRACEABILITY.parent / tok).resolve()
    if doc_rel.exists():
        return [str(doc_rel.relative_to(ROOT))]
    base = tok.rsplit("/", 1)[-1]
    hits = index.get(base, [])
    if not hits and base.endswith(".ts"):
        hits = index.get(base + "x", [])
    if "/" in tok:
        # a path-qualified token must match that tail, not just the basename
        hits = [h for h in hits if h.endswith(tok)]
    return hits


def _tokens(text: str) -> list[str]:
    pattern = r"`([A-Za-z0-9_./-]+\.(?:py|tsx|ts|md|json|toml|yaml|yml))[^`]*`"
    return sorted(set(re.findall(pattern, text)))


def test_traceability_evidence_paths_resolve() -> None:
    index = _live_index()
    dead = [
        tok
        for tok in _tokens(TRACEABILITY.read_text(encoding="utf-8"))
        if tok not in ALLOWED_MISSING and not _resolve(tok, index)
    ]
    assert not dead, (
        "EXTERNAL-REFS-TRACEABILITY.md cites evidence that no longer exists in the "
        "live source tree — a ✅ row pointing at a moved module proves nothing:\n  " + "\n  ".join(dead)
    )


def test_readme_counts_match_reality() -> None:
    """README's headline counts must be recomputed, not remembered."""
    from agent_lab.runtime_flags import FLAG_REGISTRY

    readme = README.read_text(encoding="utf-8")
    actual = {
        "flags": len(FLAG_REGISTRY),
        "regression": len([p for p in (ROOT / "sessions" / "_regression").iterdir() if p.is_dir()]),
        "routers": len(list((ROOT / "app" / "server" / "routers").glob("*.py"))),
    }

    claims = {
        "flags": re.search(r"레지스트리 \((\d+) entries\)", readme),
        "regression": re.search(r"(\d+) regression baselines", readme),
        "routers": re.search(r"`app/server/routers/` \((\d+) modules\)", readme),
    }

    wrong = []
    for key, match in claims.items():
        assert match, f"README no longer states a {key} count in the expected form"
        claimed = int(match.group(1))
        if claimed != actual[key]:
            wrong.append(f"{key}: README says {claimed}, actual {actual[key]}")

    assert not wrong, "README counts drifted from the code:\n  " + "\n  ".join(wrong)


# Links that point outside the repo on purpose. `.omo/` is an agent scratch dir,
# not tracked content — an evidence packet may cite it, but CI cannot resolve it.
ALLOWED_BROKEN_LINKS = {
    (
        "docs/redesign-2026-07/evidence/dual-write-ui-read-model-bounded-cutover-evidence-2026-07-14.md",
        "../../.omo/evidence/wave-b-m6-retire/task-7.json",
    ),
}

_LINKISH = re.compile(r"\.(md|py|ts|tsx|json|toml|yml|yaml|sh|css)$", re.I)


def _live_markdown() -> list[Path]:
    """Docs that are still maintained. `docs/archive/**` is a frozen record —
    enforcing links inside it would be churn with no reader on the other end."""
    docs = [p for p in (ROOT / "docs").rglob("*.md") if "archive" not in p.relative_to(ROOT).parts]
    docs += [ROOT / n for n in ("README.md", "CLAUDE.md", "AGENTS.md", "PRODUCT.md", "SHARED_CONTEXT.md")]
    return [p for p in docs if p.is_file()]


def test_live_docs_have_no_broken_relative_links() -> None:
    """Moving a doc must take its inbound links with it.

    Package refactors and archive moves left 148 dead relative links across 56
    files before this guard — the same rot as the traceability matrix, one level
    down. External URLs and anchors are out of scope; only file links are checked.
    """
    broken: list[str] = []
    for doc in _live_markdown():
        rel_doc = str(doc.relative_to(ROOT))
        for link in re.findall(r"\]\(([^)\s]+)\)", doc.read_text(encoding="utf-8", errors="ignore")):
            if link.startswith(("http://", "https://", "mailto:", "#")):
                continue
            path_part = link.split("#", 1)[0]
            if not path_part or not _LINKISH.search(path_part):
                continue
            if (rel_doc, link) in ALLOWED_BROKEN_LINKS:
                continue
            if not (doc.parent / path_part).resolve().exists():
                broken.append(f"{rel_doc} -> {link}")

    assert not broken, "docs link at files that do not exist:\n  " + "\n  ".join(broken)
