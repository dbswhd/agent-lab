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

import hashlib
import json
import logging
import os
from collections import defaultdict
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from agent_lab.run.state import RunStateLike
from agent_lab.wisdom.index import _tokenize

log = logging.getLogger(__name__)

_TRUE = frozenset({"1", "true", "yes", "on"})
_FALSE = frozenset({"0", "false", "no", "off"})

MIN_SAMPLE = int(os.getenv("AGENT_LAB_FEEDBACK_MIN_SAMPLE") or "3")
_PURE_CHALLENGE_YIELD_LOW = 0.3
_CRITIC_YIELD_BOOST = 0.25
_LEDGER_TAIL = 200  # max rows to read from outcomes.jsonl tail
_TOKEN_OVERLAP_MIN = 1  # min shared topic tokens to include a prior outcome


@dataclass(frozen=True)
class SetupHint:
    source: str  # "history" | "explore" | "default"
    sample_size: int  # number of prior outcomes used
    role_overrides: dict[str, str]  # agent -> role_id (empty = no change)
    suggested_subset: tuple[str, ...]  # empty = no change
    rationale: str  # human-readable reason (logged + stored in turn_metrics)
    combo_id: str = ""  # role-combo key "agent:role|..." (S1.5 attribution)
    tool_card_suggestions: tuple[str, ...] = ()  # S3a-0: installed-but-unused tool card ids


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

    Positive signals: clean pass, no repairs, consensus reached, accepted CHALLENGE.
    Negative signals: BLOCK objections (indicates role didn't resolve conflict).
    Low pure CHALLENGE yield without a critic role → penalize the combo.
    """
    from agent_lab.emergence_kpis import pure_challenge_yield_from_resolution

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
    challenge_res = (outcome.get("objection_resolution") or {}).get("CHALLENGE") or {}
    accepted_challenges = int(challenge_res.get("accepted") or 0)
    score += accepted_challenges * 0.5
    pure_rate, pure_counts = pure_challenge_yield_from_resolution(outcome.get("objection_resolution") or {})
    if pure_rate is not None and pure_rate < _PURE_CHALLENGE_YIELD_LOW and int(pure_counts.get("total") or 0) >= 1:
        roles = outcome.get("roles") or {}
        if any(str(r) == "critic" for r in roles.values()):
            score += _CRITIC_YIELD_BOOST
        else:
            score -= _CRITIC_YIELD_BOOST
    return score


def _combo_key(roles: dict[str, str]) -> str:
    """Stable role-combo key: ``agent:role|agent:role`` sorted by agent."""
    return "|".join(f"{a}:{r}" for a, r in sorted(roles.items()))


def _explore_rate() -> float:
    """ε in [0,1] for ε-greedy exploration; 0 (default) = pure exploitation."""
    raw = (os.getenv("AGENT_LAB_FEEDBACK_EXPLORE_RATE") or "0").strip()
    try:
        return max(0.0, min(1.0, float(raw)))
    except ValueError:
        return 0.0


def _explore_decision(topic: str, n: int, epsilon: float) -> bool:
    """Deterministic ε-greedy gate — no global RNG (reproducible in tests).

    Uses a topic-stable offset plus a recurring stride so repeated runs over the
    same benchmark set eventually produce explore rows. This preserves OFF-parity
    at ε=0, force-explore at ε>=1, and keeps the schedule reproducible.
    """
    if epsilon <= 0.0:
        return False
    if epsilon >= 1.0:
        return True
    stride = max(1, round(1.0 / epsilon))
    digest = hashlib.sha1(topic.encode("utf-8")).hexdigest()
    offset = int(digest[:8], 16) % stride
    return n % stride == offset


def _mutate_combo(roles: dict[str, str]) -> dict[str, str]:
    """Produce a novel combo by reassigning one agent to a different role.

    Deterministic: targets the alphabetically-first agent, prefers an unused
    role (max diversity), else any role != current.
    """
    if not roles:
        return {}
    from agent_lab.role_plan import _ROLES

    target = sorted(roles)[0]
    current = roles[target]
    used = set(roles.values())
    candidates = [r for r in sorted(_ROLES) if r not in used] or [r for r in sorted(_ROLES) if r != current]
    if not candidates:
        return dict(roles)
    mutated = dict(roles)
    mutated[target] = candidates[0]
    return mutated


def _explore_combo(
    combo_scores: dict[str, list[float]],
    combo_roles: dict[str, dict[str, str]],
) -> tuple[dict[str, str], str]:
    """Pick an exploration target: least-sampled known combo, or a mutation.

    ≥2 known combos → least-sampled (UCB spirit, deterministic tie-break by key).
    1 known combo  → mutate it into a fresh combo so the space actually widens.
    """
    if len(combo_scores) >= 2:
        key = min(sorted(combo_scores), key=lambda k: len(combo_scores[k]))
        return dict(combo_roles[key]), key
    only_key = next(iter(combo_roles))
    mutated = _mutate_combo(combo_roles[only_key])
    return mutated, _combo_key(mutated)


def _advisor_enabled(*, room_preset: str = "") -> bool:
    from agent_lab.s1_flags import s1_flag_enabled

    return s1_flag_enabled("AGENT_LAB_FEEDBACK_ADVISOR", room_preset=room_preset)


def _with_tool_card_note(hint: SetupHint, category: str, run_meta: RunStateLike | None) -> SetupHint:
    """S3a-0 — append installed-but-unused tool card suggestions (RECALL input, not a new loop).

    Context annotation only, same as ``_wisdom_note``: never changes role_overrides
    or suggested_subset, applies regardless of which branch produced ``hint``.
    """
    from agent_lab.tool_cards import tool_card_note

    note, ids = tool_card_note(category, run_meta)
    if not note:
        return hint
    suffix = f" | tool_cards:{note}"
    return replace(hint, rationale=hint.rationale + suffix, tool_card_suggestions=ids)


def advise_setup(
    topic: str,
    category: str,
    available_agents: list[str],
    *,
    root: Path | None = None,
    room_preset: str = "",
    run_meta: RunStateLike | None = None,
) -> SetupHint:
    """Read outcomes.jsonl and return a SetupHint for the current turn.

    Falls back to ``_DEFAULT_HINT`` on any error or insufficient history.
    """
    if not _advisor_enabled(room_preset=room_preset):
        return _DEFAULT_HINT

    try:
        hint = _advise_inner(topic, category, available_agents, root=root)
    except Exception:
        # Distinct rationale from _DEFAULT_HINT's "no_history" so feedback_report
        # can tell a genuine cold-start apart from an advisor bug swallowed here.
        log.warning("advise_setup failed", exc_info=True)
        hint = replace(_DEFAULT_HINT, rationale="advisor_error")
    return _with_tool_card_note(hint, category, run_meta)


def _wisdom_note(topic: str, *, limit: int = 3) -> str:
    """Return a compact note from cross-session [LEARNED:] wisdom hits, or ''.

    Uses the existing AGENT_LAB_WISDOM_CROSS_SESSION flag — returns '' when off.
    Role decisions are NOT affected; this is context annotation only.
    """
    try:
        from agent_lab.wisdom.index import search_wisdom_cross_sessions

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
    relevant_all: list[dict[str, Any]] = []
    for row in rows:
        if str(row.get("category") or "") != category:
            continue
        row_terms = set(row.get("topic_terms") or [])
        if not topic_tokens or not row_terms:
            overlap = 0
        else:
            overlap = len(topic_tokens & row_terms)
        if overlap >= _TOKEN_OVERLAP_MIN:
            relevant_all.append(row)

    # Prefer phase=execute rows (real Oracle verdicts) over turn-only rows —
    # mirrors feedback_report._is_verdict_eligible. Fall back to the full pool
    # (turn rows included) when execute evidence is too thin so cold-start
    # behavior is unchanged (see NORTH-STAR §1 S1 관측 절차).
    relevant_execute = [row for row in relevant_all if str(row.get("phase") or "") == "execute"]
    if len(relevant_execute) >= MIN_SAMPLE:
        relevant = relevant_execute
        evidence = "execute"
    else:
        relevant = relevant_all
        evidence = "turn_fallback"

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
        key = _combo_key(filtered_roles)
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

    # Phase C: augment rationale with cross-session [LEARNED:] wisdom snippets.
    # Role decisions are NOT affected — wisdom is context-injection only.
    wisdom_note = _wisdom_note(topic)
    wisdom_suffix = f" | wisdom:{wisdom_note}" if wisdom_note else ""

    # S1.5: ε-greedy — occasionally try a non-best/novel combo so the loop can
    # discover better setups instead of locking onto the first winner. ε=0
    # (default) skips this entirely → identical to pure exploitation (OFF-parity).
    if _explore_decision(topic, len(relevant), _explore_rate()):
        explore_roles, explore_key = _explore_combo(combo_scores, combo_roles)
        if explore_roles:
            return SetupHint(
                source="explore",
                sample_size=len(relevant),
                role_overrides=dict(explore_roles),
                suggested_subset=(),
                rationale=(
                    f"explore(combo={explore_key},evidence={evidence}):"
                    + ",".join(f"{a}→{r}" for a, r in sorted(explore_roles.items()))
                    + wisdom_suffix
                ),
                combo_id=explore_key,
            )

    # Exploit: pick the highest average-score combo
    best_key = max(combo_scores, key=lambda k: sum(combo_scores[k]) / len(combo_scores[k]))
    best_roles = combo_roles[best_key]
    best_n = len(combo_scores[best_key])
    best_avg = sum(combo_scores[best_key]) / best_n

    from agent_lab.s2_role_bandit import subset_from_role_combo

    return SetupHint(
        source="history",
        sample_size=len(relevant),
        role_overrides=dict(best_roles),
        suggested_subset=subset_from_role_combo(best_roles, available_agents),
        rationale=(
            f"best_combo(n={best_n},avg_score={best_avg:.2f},evidence={evidence}):"
            + ",".join(f"{a}→{r}" for a, r in sorted(best_roles.items()))
            + wisdom_suffix
        ),
        combo_id=best_key,
    )
