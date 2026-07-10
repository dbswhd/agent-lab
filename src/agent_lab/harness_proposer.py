"""HS3 PROPOSE — bounded harness-patch candidates.

Flag-gated (``AGENT_LAB_HARNESS_PROPOSER``, default off). See
docs/DESIGN-HARNESS-SELF-IMPROVE.md §7, §8.4, §9 HS3.

This module does **not** generate diff content and does **not** call an LLM —
"offline script 우선" (HS3-5) means a human (or, later, a Room agent) authors
the actual change and submits it here; this module only *bounds and
validates* the submission against four independent gates before it becomes a
registered ``PatchCandidate``:

1. **STOP guard** (§7.4) — mock agents / fast profile / sub-L2 autonomy block
   proposal entirely.
2. **Tier** (§7) — every touched file must resolve to the same Tier (A or B)
   in ``.agent-lab/harness/manifest.json``; Tier C (frozen or unregistered)
   rejects the whole candidate.
3. **Axis** (REVIEW P1-3) — every touched file must share one manifest
   ``axis`` (prompts/preset/profile/skills/hooks/ui/eval_surface); a
   candidate spanning axes is rejected outright rather than risking
   creative-but-unbounded multi-surface edits.
4. **Eval surface** (HS3-6/REVIEW P0-5) — a candidate that introduces a new
   surface must carry ``eval_additions`` (a dogfood topic or evals case id);
   HS4-6 enforces this again at the regression gate, this is the proposer's
   own half of the same rule.

``manifest.json`` is the single git-tracked SSOT for editable-surface tiers
(HS3-2) — ``self_patch.py``'s allowlist now reads its Tier A globs from here
instead of maintaining a second list.

``PatchCandidate.assertions`` (pytest node ids) is optional here — HS4-1
(regression_gate.py) is what actually *requires* it non-empty before running
a candidate through the worktree gate; propose-time only carries it through.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from agent_lab.time_utils import utc_now_iso_seconds as _now_iso
from agent_lab.env_flags import env_bool
from agent_lab.run.state import RunStateLike

MANIFEST_SCHEMA_VERSION = 1

DEFAULT_MANIFEST: dict[str, Any] = {
    "schema_version": MANIFEST_SCHEMA_VERSION,
    "tiers": {
        "A": [
            {"glob": ".claude/skills/**", "edit_unit": "file", "axis": "skills"},
            {
                "glob": "src/agent_lab/agents/prompts.py",
                "edit_unit": "block",
                "marker": "# --- BLOCK:",
                "axis": "prompts",
            },
            {"glob": "src/agent_lab/run/profile.py", "edit_unit": "file", "axis": "profile"},
            {"glob": "src/agent_lab/room/preset.py", "edit_unit": "file", "axis": "preset"},
        ],
        "B": [
            {"glob": ".agent-lab/hooks.toml", "edit_unit": "file", "axis": "hooks", "requires": ["inbox_full"]},
            {
                "glob": "web/src/hooks/useRoomComposerPrefs.ts",
                "edit_unit": "file",
                "axis": "ui",
                "requires": ["inbox_full", "web_build"],
            },
            {
                "glob": "web/src/hooks/useRoomExecuteSend.ts",
                "edit_unit": "file",
                "axis": "ui",
                "requires": ["inbox_full", "smoke"],
            },
            {
                "glob": "evals/cases.jsonl",
                "edit_unit": "file",
                "axis": "eval_surface",
                "requires": ["inbox_full", "held_out_audit"],
            },
            {
                "glob": "sessions/_benchmark/topics/dogfood-v1.json",
                "edit_unit": "file",
                "axis": "eval_surface",
                "requires": ["inbox_full", "held_out_audit"],
            },
        ],
    },
    "frozen_prefixes": [
        "src/agent_lab/room/turn_flow",
        "src/agent_lab/room/agent_invoke.py",
        "src/agent_lab/plan/execute",
        "src/agent_lab/human_inbox.py",
        "src/agent_lab/runtime/",
        "app/server/routers/room.py",
        "src/agent_lab/outcome_harvester.py",
        "src/agent_lab/feedback_advisor.py",
    ],
}


class ProposalRejected(Exception):
    """A candidate failed the STOP guard, tier, axis, or eval-surface gate."""


def harness_proposer_enabled() -> bool:
    """AGENT_LAB_HARNESS_PROPOSER (default off)."""
    return env_bool("AGENT_LAB_HARNESS_PROPOSER")



# ---------------------------------------------------------------------------
# manifest.json — SSOT (HS3-2)
# ---------------------------------------------------------------------------


def manifest_path(root: Path | None = None) -> Path:
    from agent_lab.outcome_harvester import agent_lab_project_root

    return agent_lab_project_root(root) / ".agent-lab" / "harness" / "manifest.json"


def ensure_manifest(root: Path | None = None) -> Path:
    """Create manifest.json with the documented defaults if absent (git-tracked SSOT)."""
    path = manifest_path(root)
    if not path.is_file():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(DEFAULT_MANIFEST, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def load_manifest(root: Path | None = None) -> dict[str, Any]:
    """Read manifest.json, or the in-memory default when absent (non-mutating)."""
    path = manifest_path(root)
    if not path.is_file():
        return json.loads(json.dumps(DEFAULT_MANIFEST))
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return json.loads(json.dumps(DEFAULT_MANIFEST))
    return data if isinstance(data, dict) else json.loads(json.dumps(DEFAULT_MANIFEST))


def _tier_entries(manifest: dict[str, Any], tier: str) -> list[dict[str, Any]]:
    entries = (manifest.get("tiers") or {}).get(tier, [])
    return [e for e in entries if isinstance(e, dict) and e.get("glob")]


def tier_a_globs(manifest: dict[str, Any] | None = None, *, root: Path | None = None) -> list[str]:
    m = manifest or load_manifest(root)
    return [e["glob"] for e in _tier_entries(m, "A")]


def tier_b_globs(manifest: dict[str, Any] | None = None, *, root: Path | None = None) -> list[str]:
    m = manifest or load_manifest(root)
    return [e["glob"] for e in _tier_entries(m, "B")]


# --- glob matching (moved from self_patch.py — this module is now the SSOT) -


def _pattern_to_regex(pattern: str) -> re.Pattern[str]:
    """Gitignore-style glob: '**' matches any depth, '*' stays within one segment."""
    placeholder = "\x00DOUBLESTAR\x00"
    escaped = re.escape(pattern.strip("/")).replace(re.escape("**"), placeholder)
    escaped = escaped.replace(re.escape("*"), "[^/]*")
    escaped = escaped.replace(placeholder, ".*")
    return re.compile(f"^{escaped}$")


def normalize_path(path: str) -> str:
    return str(path).strip().replace("\\", "/").lstrip("/")


def _glob_matches(path: str, glob: str) -> bool:
    return bool(_pattern_to_regex(glob).match(normalize_path(path)))


def manifest_entry_for_path(
    path: str, manifest: dict[str, Any] | None = None, *, root: Path | None = None
) -> dict[str, Any] | None:
    """The first Tier A/B entry whose glob matches ``path``, or None (Tier C)."""
    m = manifest or load_manifest(root)
    for tier in ("A", "B"):
        for entry in _tier_entries(m, tier):
            if _glob_matches(path, entry["glob"]):
                return {**entry, "tier": tier}
    return None


def classify_tier(path: str, manifest: dict[str, Any] | None = None, *, root: Path | None = None) -> str:
    """'A' or 'B' on a manifest match; 'C' otherwise (frozen or unregistered — §7.3 both reject)."""
    entry = manifest_entry_for_path(path, manifest, root=root)
    return entry["tier"] if entry else "C"


def axis_for_path(path: str, manifest: dict[str, Any] | None = None, *, root: Path | None = None) -> str | None:
    entry = manifest_entry_for_path(path, manifest, root=root)
    return str(entry["axis"]) if entry and entry.get("axis") else None


# ---------------------------------------------------------------------------
# prompts.py BLOCK parser (HS3-3)
# ---------------------------------------------------------------------------

_BLOCK_START_RE = re.compile(r"^#\s*---\s*BLOCK:\s*(\S+)\s*---\s*$")
_BLOCK_END_RE = re.compile(r"^#\s*---\s*END BLOCK:\s*(\S+)\s*---\s*$")


def parse_prompt_blocks(text: str) -> dict[str, tuple[int, int]]:
    """``{agent: (start_line, end_line)}`` (1-indexed, inclusive) from
    ``# --- BLOCK: {agent} ---`` / ``# --- END BLOCK: {agent} ---`` marker pairs.

    An unclosed or mismatched BLOCK is silently dropped — callers treat a
    missing agent key as "no declared block", not as a parse error.
    """
    blocks: dict[str, tuple[int, int]] = {}
    open_agent: str | None = None
    open_line = 0
    for i, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        m = _BLOCK_START_RE.match(stripped)
        if m:
            open_agent, open_line = m.group(1), i
            continue
        m = _BLOCK_END_RE.match(stripped)
        if m and open_agent == m.group(1):
            blocks[open_agent] = (open_line, i)
            open_agent = None
    return blocks


# ---------------------------------------------------------------------------
# STOP guard (§7.4)
# ---------------------------------------------------------------------------


def stop_guard_reason(*, run_meta: RunStateLike | None = None) -> str | None:
    """None when the proposer may run; otherwise the human-readable STOP reason.

    ``autonomy.level < L2`` only applies when ``run_meta`` is supplied (the
    Room-optional path) — the offline-script primary path (HS3-5) has no
    active session to check, and PROPOSE itself never merges, so a missing
    autonomy ceiling doesn't block drafting a candidate.
    """
    if env_bool("AGENT_LAB_MOCK_AGENTS"):
        return "AGENT_LAB_MOCK_AGENTS=1 (STOP: 약모델 재귀개선 금지)"
    from agent_lab.run.profile import default_run_profile

    # "model tier < balanced" folds into this check — run profile is the only
    # model-tier proxy this codebase has; fast profile implies a single lead
    # without the mechanism-improvement capability §7.4 requires.
    if default_run_profile() == "fast":
        return "AGENT_LAB_RUN_PROFILE=fast (단일 lead — model tier < balanced와 동형)"
    if run_meta is not None:
        from agent_lab.autonomy_ladder import infer_effective_autonomy_level

        level = infer_effective_autonomy_level(run_meta)
        if level in ("L0", "L1"):
            return f"autonomy.level={level} < L2"
    return None


# ---------------------------------------------------------------------------
# HS3-4 trigger — addressable weakness patterns
# ---------------------------------------------------------------------------


def addressable_patterns(*, root: Path | None = None) -> list[dict[str, Any]]:
    """Weakness patterns that cleared HS1's recurrence threshold (addressable=True)."""
    from agent_lab.weakness_miner import mine_weakness_patterns

    report = mine_weakness_patterns(root)
    return [p for p in report.get("patterns", []) if p.get("addressable")]


# ---------------------------------------------------------------------------
# PatchCandidate (§8.4)
# ---------------------------------------------------------------------------


@dataclass
class PatchCandidate:
    id: str
    pattern_id: str
    axis: str
    files: list[str]
    diff_ref: str
    eval_additions: list[str]
    assertions: list[str]
    tier: str
    harness_rev: str
    status: str
    created_at: str


def _candidate_id(pattern_id: str) -> str:
    # Hyphen-only — this id becomes a directory name in write_candidate(),
    # so no ':' (unsafe on some filesystems/tools despite being valid POSIX).
    ts = _now_iso()
    digest = hashlib.sha1(f"{ts}:{pattern_id}".encode()).hexdigest()[:8]
    return f"pc-{ts[:10]}-{digest}"


def propose_candidate(
    *,
    pattern_id: str,
    axis: str,
    files: list[str],
    diff_ref: str,
    eval_additions: list[str] | None = None,
    assertions: list[str] | None = None,
    introduces_new_surface: bool = False,
    block: str | None = None,
    run_meta: RunStateLike | None = None,
    root: Path | None = None,
) -> PatchCandidate:
    """Validate a human/agent-authored change against the four PROPOSE gates
    and return a registered ``PatchCandidate``. Raises ``ProposalRejected``
    (with the specific reason) on any gate failure — never partially accepts."""
    reason = stop_guard_reason(run_meta=run_meta)
    if reason:
        raise ProposalRejected(f"STOP guard: {reason}")
    if not files:
        raise ProposalRejected("candidate must touch at least one file")

    manifest = load_manifest(root)
    tiers = {classify_tier(f, manifest) for f in files}
    if "C" in tiers:
        rejected = [f for f in files if classify_tier(f, manifest) == "C"]
        raise ProposalRejected(f"Tier C (frozen or unregistered) files in candidate: {rejected}")
    if len(tiers) > 1:
        raise ProposalRejected(f"candidate spans multiple tiers {sorted(tiers)} — reject, one tier per candidate")
    tier = next(iter(tiers))

    axes = {axis_for_path(f, manifest) for f in files}
    if len(axes) > 1 or axis not in axes:
        raise ProposalRejected(
            f"REVIEW P1-3 (1 candidate = 1 axis): files resolve to axes {sorted(a for a in axes if a)}, "
            f"declared axis={axis!r}"
        )

    for f in files:
        entry = manifest_entry_for_path(f, manifest)
        if entry and entry.get("edit_unit") == "block":
            if not block:
                raise ProposalRejected(f"{f} is block-scoped ({entry.get('marker')}) — 'block' (agent name) required")
            target = Path(root) / f if root is not None else Path(f)
            if target.is_file():
                blocks = parse_prompt_blocks(target.read_text(encoding="utf-8"))
                if block not in blocks:
                    raise ProposalRejected(f"no '{block}' BLOCK found in {f}")

    if introduces_new_surface and not eval_additions:
        raise ProposalRejected("HS3-6/REVIEW P0-5: new surface requires eval_additions (dogfood topic or evals case)")

    from agent_lab.wisdom.playbook import HARNESS_REV_UNSET

    return PatchCandidate(
        id=_candidate_id(pattern_id),
        pattern_id=pattern_id,
        axis=axis,
        files=list(files),
        diff_ref=diff_ref,
        eval_additions=list(eval_additions or []),
        assertions=list(assertions or []),
        tier=tier,
        harness_rev=HARNESS_REV_UNSET,
        status="proposed",
        created_at=_now_iso(),
    )


def candidates_root(root: Path | None = None) -> Path:
    from agent_lab.outcome_harvester import agent_lab_project_root

    return agent_lab_project_root(root) / ".agent-lab" / "harness" / "candidates"


def write_candidate(candidate: PatchCandidate, *, root: Path | None = None) -> Path:
    """Append-only: refuses to overwrite an existing candidate file."""
    path = candidates_root(root) / candidate.id / "candidate.json"
    if path.exists():
        raise FileExistsError(f"candidate already written: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(candidate), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def load_candidate(candidate_id: str, *, root: Path | None = None) -> dict[str, Any]:
    """Read a written candidate.json back (HS4 REGRESS consumer)."""
    path = candidates_root(root) / candidate_id / "candidate.json"
    if not path.is_file():
        raise FileNotFoundError(f"candidate not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"malformed candidate file: {path}")
    return data


__all__ = [
    "DEFAULT_MANIFEST",
    "ProposalRejected",
    "PatchCandidate",
    "harness_proposer_enabled",
    "manifest_path",
    "ensure_manifest",
    "load_manifest",
    "tier_a_globs",
    "tier_b_globs",
    "normalize_path",
    "manifest_entry_for_path",
    "classify_tier",
    "axis_for_path",
    "parse_prompt_blocks",
    "stop_guard_reason",
    "addressable_patterns",
    "propose_candidate",
    "candidates_root",
    "write_candidate",
    "load_candidate",
]
