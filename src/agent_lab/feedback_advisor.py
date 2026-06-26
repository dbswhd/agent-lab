"""S1 Phase B — feedback advisor: cross-session RECALL → SetupHint.

Reads the outcome ledger (.agent-lab/outcomes.jsonl) built by Phase A and
produces a ``SetupHint`` that shapes role assignment and agent-subset selection
for the next turn.

Fail-open contract:
- Any error (missing ledger, bad JSON, …) returns a default-source empty hint.
- ``sample_size < MIN_SAMPLE`` (default 3) → default-source hint (no override).
- The hint **only** adjusts role text and agent selection — it has no path to
  weaken BLOCK→409, worktree isolation, Oracle gates, or Human Inbox.

See docs/DESIGN-S1-FEEDBACK-LOOP.md (Phase B).
"""

from __future__ import annotations

import json
import logging
import os
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent_lab.wisdom_index import _tokenize

log = logging.getLogger(__name__)

_TRUE = frozenset({"1", "true", "yes", "on"})

MIN_SAMPLE = int(os.getenv("AGENT_LAB_FEEDBACK_MIN_SAMPLE") or "3")
_LEDGER_TAIL = 200  # max rows to read from outcomes.jsonl tail
_TOKEN_OVERLAP_MIN = 1  # min shared topic tokens to include a prior outcome


@dataclass(frozen=True)
class SetupHint:
    source: str  # "history" | "default"
    sample_size: int  # number of prior outcomes used
    role_overrides: dict[str, str]  # agent -> role_id (empty = no change)
    suggested_subset: tuple[str, ...]  # empty = no change
    rationale: str  # human-readable reason (logged + stored in turn_metrics)


_DEFAULT_HINT = SetupHint(
    source="default",
    sample_size=0,
    role_overrides={},
    suggested_subset=(),
    rationale="no_history",
)


def _flag_on(name: str) -> bool:
    return (os.getenv(name) or "").strip().lower() in _TRUE


def _outcomes_path(root: Path | None) -> Path:
    from agent_lab.outcome_harvester import outcomes_path

    return outcomes_path(root)


def _load_tail(path: Path, n: int) -> list[dict[str, Any]]:
    """Read up to ``n`` most-recent lines from a JSONL file."""
    if not path.is_file():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    rows: list[dict[str, Any]] = []
    for line in lines[-n:]:
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def _score_outcome(outcome: dict[str, Any]) -> float:
    """Score a single prior outcome for role-combo quality.

    Positive signals: clean pass, no repairs, consensus reached.
    Negative signals: BLOCK objections (indicates role didn't resolve conflict).
    """
    score = 0.0
    verdict = str(outcome.get("final_verdict") or "").lower()
    repair = int(outcome.get("repair_attempts") or 0)
    if verdict == "pass" and repair == 0:
        score += 2.0
    elif verdict == "pass":
        score += 1.0
    elif verdict == "fail":
        score -= 1.0
    if outcome.get("consensus_reached"):
        score += 0.5
    blocks = int((outcome.get("objection_summary") or {}).get("BLOCK", 0))
    score -= blocks * 1.0
    return score


def advise_setup(
    topic: str,
    category: str,
    available_agents: list[str],
    *,
    root: Path | None = None,
) -> SetupHint:
    """Read outcomes.jsonl and return a SetupHint for the current turn.

    Falls back to ``_DEFAULT_HINT`` on any error or insufficient history.
    """
    if not _flag_on("AGENT_LAB_FEEDBACK_ADVISOR"):
        return _DEFAULT_HINT

    try:
        return _advise_inner(topic, category, available_agents, root=root)
    except Exception:
        log.warning("advise_setup failed", exc_info=True)
        return _DEFAULT_HINT


def _wisdom_note(topic: str, *, limit: int = 3) -> str:
    """Return a compact note from cross-session [LEARNED:] wisdom hits, or ''.

    Uses the existing AGENT_LAB_WISDOM_CROSS_SESSION flag — returns '' when off.
    Role decisions are NOT affected; this is context annotation only.
    """
    try:
        from agent_lab.wisdom_index import search_wisdom_cross_sessions

        hits = search_wisdom_cross_sessions(topic, limit=limit)
        if not hits:
            return ""
        snippets = [str(h.get("snippet") or h.get("title") or "").strip()[:120] for h in hits if h]
        snippets = [s for s in snippets if s]
        return "; ".join(snippets[:limit]) if snippets else ""
    except Exception:
        return ""


def _advise_inner(
    topic: str,
    category: str,
    available_agents: list[str],
    *,
    root: Path | None,
) -> SetupHint:
    path = _outcomes_path(root)
    rows = _load_tail(path, _LEDGER_TAIL)
    if not rows:
        return _DEFAULT_HINT

    topic_tokens = _tokenize(topic)

    # Filter: same category + sufficient topic token overlap
    relevant: list[dict[str, Any]] = []
    for row in rows:
        if str(row.get("category") or "") != category:
            continue
        row_terms = set(row.get("topic_terms") or [])
        if not topic_tokens or not row_terms:
            overlap = 0
        else:
            overlap = len(topic_tokens & row_terms)
        if overlap >= _TOKEN_OVERLAP_MIN:
            relevant.append(row)

    if len(relevant) < MIN_SAMPLE:
        return SetupHint(
            source="default",
            sample_size=len(relevant),
            role_overrides={},
            suggested_subset=(),
            rationale=f"insufficient_history(n={len(relevant)},min={MIN_SAMPLE})",
        )

    # Aggregate: score each outcome, accumulate per role-combo
    # role_combo key = frozenset of "agent:role" pairs for available agents
    combo_scores: dict[str, list[float]] = defaultdict(list)
    combo_roles: dict[str, dict[str, str]] = {}

    for outcome in relevant:
        roles: dict[str, str] = outcome.get("roles") or {}
        # Only consider role combos that involve current available agents
        filtered_roles = {a: r for a, r in roles.items() if a in available_agents and r}
        if not filtered_roles:
            continue
        key = "|".join(f"{a}:{r}" for a, r in sorted(filtered_roles.items()))
        combo_scores[key].append(_score_outcome(outcome))
        combo_roles[key] = filtered_roles

    if not combo_scores:
        return SetupHint(
            source="default",
            sample_size=len(relevant),
            role_overrides={},
            suggested_subset=(),
            rationale="no_role_combos_for_available_agents",
        )

    # Pick the highest average-score combo
    best_key = max(combo_scores, key=lambda k: sum(combo_scores[k]) / len(combo_scores[k]))
    best_roles = combo_roles[best_key]
    best_n = len(combo_scores[best_key])
    best_avg = sum(combo_scores[best_key]) / best_n

    # Phase C: augment rationale with cross-session [LEARNED:] wisdom snippets.
    # Role decisions are NOT affected — wisdom is context-injection only.
    wisdom_note = _wisdom_note(topic)

    return SetupHint(
        source="history",
        sample_size=len(relevant),
        role_overrides=dict(best_roles),
        suggested_subset=(),
        rationale=(
            f"best_combo(n={best_n},avg_score={best_avg:.2f}):"
            + ",".join(f"{a}→{r}" for a, r in sorted(best_roles.items()))
            + (f" | wisdom:{wisdom_note}" if wisdom_note else "")
        ),
    )
