"""Clarity gate for the CLARIFY phase (AGENT_LAB_PIPELINE) — gjc deep-interview analog.

Elevated from a single-agent float scorer to a multi-agent *lateral clarification panel*:

* Multi-dimensional scoring (goal / constraints / criteria / context), mirroring gjc
  deep-interview's per-dimension ambiguity.
* Coverage-weighted weakest aggregation (``0.6*max + 0.4*mean`` in ambiguity terms) so the
  vaguest dimension dominates — the same formula gjc uses to target the weakest dimension.
* A lateral panel: every available agent scores all dimensions from its own lens; the spread
  across panelists is the lateral signal. Aggregation is the per-dimension mean.
* A real question loop: when ambiguity is above threshold, dimension-targeted clarifying
  questions are generated and persisted through ``session_clarifier``; answers are folded back
  into the clarity text and re-scored until ambiguity drops to/below the threshold.

Concrete-anchor detection still short-circuits: anchored tasks skip CLARIFY entirely.
Everything is mock-safe and deterministic under ``AGENT_LAB_MOCK_AGENTS=1``.
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from typing import Any

# Default ambiguity threshold; override via AGENT_LAB_CLARITY_THRESHOLD.
CLARITY_AMBIGUITY_THRESHOLD = 0.30

# Requirement-clarity dimensions (gjc deep-interview parity).
CLARITY_DIMENSIONS: tuple[str, ...] = ("goal", "constraints", "criteria", "context")

# Cap the lateral panel so live scoring stays one call per panelist, bounded.
_MAX_PANEL = 3

_ANCHOR_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"[\w./-]+\.[A-Za-z]{1,6}\b"),  # file path with extension
    re.compile(r"#\d+"),  # issue / PR number
    re.compile(r"\b[a-z][a-z0-9]*[A-Z][A-Za-z0-9]*\b"),  # camelCase
    re.compile(r"\b[A-Z][a-z0-9]+[A-Z][A-Za-z0-9]*\b"),  # PascalCase
    re.compile(r"\b[a-z0-9]+_[a-z0-9_]+\b"),  # snake_case
    re.compile(r"(?i)acceptance criteria"),
    re.compile(r"```"),  # code block
)

_PANEL_SYSTEM = (
    "You are one panelist on a requirements-clarity panel. Score how AMBIGUOUS the development "
    "task is on each dimension, from 0.0 (crystal clear, ready to build) to 1.0 (utterly vague):\n"
    "- goal: what outcome / definition of done\n"
    "- constraints: limits, dependencies, must-not-touch\n"
    "- criteria: how completion is verified (tests/commands/outputs)\n"
    "- context: target paths/modules and scope boundaries\n"
    "Reply with ONLY: goal=<f> constraints=<f> criteria=<f> context=<f>"
)

# Deterministic per-dimension clarifying questions (lateral panel fallback + mock).
_DIMENSION_QUESTIONS: dict[str, str] = {
    "goal": "이번 작업의 최종 산출물과 'done'의 정의를 한 줄로 적어 주세요.",
    "constraints": "지켜야 할 제약(건드리면 안 되는 것·의존성·시간)이 있나요?",
    "criteria": "완료를 무엇으로 검증하나요? (테스트·명령·기대 출력)",
    "context": "대상 경로/모듈과 의도적으로 제외할 범위는 어디인가요?",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _threshold() -> float:
    raw = os.getenv("AGENT_LAB_CLARITY_THRESHOLD", "").strip()
    if raw:
        try:
            return float(raw)
        except ValueError:
            pass
    return CLARITY_AMBIGUITY_THRESHOLD


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def topology_enabled() -> bool:
    """AGENT_LAB_CLARITY_TOPOLOGY (default OFF): add component-level decomposition + scoring.

    Off keeps simple missions cheap (global 4-dimension panel only). On adds exactly one extra
    agent call to decompose the task into components and score each, so questions can target the
    vaguest *part* — gjc deep-interview topology parity.
    """
    return _env_bool("AGENT_LAB_CLARITY_TOPOLOGY")


def detect_concrete_anchors(text: str) -> bool:
    """True when the task carries a concrete anchor (file/symbol/issue/criteria/code block)."""
    return any(pattern.search(text or "") for pattern in _ANCHOR_PATTERNS)


def _mission_clarity_text(run: dict[str, Any]) -> str:
    """Clarity input = goal/topic/clarify_task PLUS any answered clarifier Q&A.

    Folding answers in means the real question loop reduces ambiguity: each concrete answer
    adds signal (and often anchors), pushing the score toward the threshold.
    """
    loop = run.get("verified_loop")
    loop = loop if isinstance(loop, dict) else {}
    goal = loop.get("loop_goal")
    goal = goal if isinstance(goal, dict) else {}
    ml = run.get("mission_loop")
    ml = ml if isinstance(ml, dict) else {}
    parts = [goal.get("text"), run.get("topic"), ml.get("clarify_task")]
    interview = run.get("clarifier_interview")
    if isinstance(interview, dict):
        answers = interview.get("answers") if isinstance(interview.get("answers"), dict) else {}
        for q in interview.get("questions") or []:
            if not isinstance(q, dict):
                continue
            ans = str(answers.get(str(q.get("id") or ""), "") or "").strip()
            if ans:
                parts.append(ans)
    return " ".join(str(p) for p in parts if p).strip()


def _parse_score(reply: str) -> float:
    """Backward-compatible single-float parse (conservative on miss)."""
    match = re.search(r"(0(?:\.\d+)?|1(?:\.0+)?)", reply or "")
    if not match:
        return 0.8  # conservative: unparseable => needs clarification
    try:
        return max(0.0, min(1.0, float(match.group(1))))
    except ValueError:
        return 0.8


def _parse_dimension_reply(reply: str) -> dict[str, float]:
    out: dict[str, float] = {}
    for dim in CLARITY_DIMENSIONS:
        match = re.search(rf"{dim}\s*[=:]\s*(0(?:\.\d+)?|1(?:\.0+)?)", reply or "", re.IGNORECASE)
        if not match:
            continue
        try:
            out[dim] = max(0.0, min(1.0, float(match.group(1))))
        except ValueError:
            continue
    return out


def _coverage_weighted_overall(dimensions: dict[str, float]) -> float:
    """gjc-style coverage-weighted weakest: the vaguest dimension dominates."""
    vals = [float(v) for v in dimensions.values()]
    if not vals:
        return 0.8
    return round(0.6 * max(vals) + 0.4 * (sum(vals) / len(vals)), 4)


def _mock_dimension_scores(text: str) -> dict[str, float]:
    """Deterministic per-dimension ambiguity for tests / mock runs.

    Uniform vague text scores 0.8 on every dimension (overall 0.8, preserving the legacy
    single-float mock contract); concrete signals lower the matching dimension.
    """
    if not text.strip():
        return {dim: 1.0 for dim in CLARITY_DIMENSIONS}
    if detect_concrete_anchors(text):
        return {dim: 0.0 for dim in CLARITY_DIMENSIONS}
    scores = {dim: 0.8 for dim in CLARITY_DIMENSIONS}
    low = text.lower()
    if re.search(r"(?i)verify|verif|test|검증|acceptance|criteria|기대 출력|expected output", low):
        scores["criteria"] = 0.3
    if re.search(r"(?i)scope|범위|module|모듈|path|경로|directory|디렉터리|src/|under ", low):
        scores["context"] = 0.4
    if re.search(r"(?i)must|don'?t|do not|금지|제약|constraint|dependency|의존|deadline|시간", low):
        scores["constraints"] = 0.4
    if len(text) >= 80:
        scores["goal"] = min(scores["goal"], 0.6)
    return scores


def _build_result(dimensions: dict[str, float], per_agent: dict[str, dict[str, float]]) -> dict[str, Any]:
    overall = _coverage_weighted_overall(dimensions)
    weakest = max(dimensions, key=lambda d: dimensions[d]) if dimensions else None
    # weakest only meaningful when there is residual ambiguity
    if weakest is not None and dimensions.get(weakest, 0.0) <= 0.0:
        weakest = None
    return {
        "dimensions": dimensions,
        "overall": overall,
        "weakest": weakest,
        "per_agent": per_agent,
        "panel": list(per_agent.keys()),
    }


_TOPOLOGY_SYSTEM = (
    "Decompose the development task into 2-4 components (subsystems / areas of work). For EACH "
    "component, score how AMBIGUOUS it is 0.0..1.0 on goal/constraints/criteria/context. Reply with "
    "one line per component, nothing else:\n"
    "component=<short-name> | goal=<f> constraints=<f> criteria=<f> context=<f>"
)


def _mock_split_components(text: str) -> list[tuple[str, str]]:
    """Deterministic component split for tests / mock runs."""
    parts = re.split(r"\s*(?:,|;|→|->| and | then |그리고|및|이후)\s*", text)
    parts = [p.strip() for p in parts if p.strip()]
    if len(parts) <= 1:
        return [("overall", text)]
    out: list[tuple[str, str]] = []
    for index, part in enumerate(parts[:4]):
        name = "-".join(part.lower().split()[:3]) or f"part{index + 1}"
        out.append((name, part))
    return out


def _parse_topology_reply(reply: str) -> list[tuple[str, dict[str, float]]]:
    components: list[tuple[str, dict[str, float]]] = []
    for line in (reply or "").splitlines():
        match = re.search(r"component\s*[=:]\s*([^|]+)\|(.*)", line, re.IGNORECASE)
        if not match:
            continue
        name = match.group(1).strip()
        if not name:
            continue
        dims = _parse_dimension_reply(match.group(2))
        components.append((name, {dim: dims.get(dim, 0.8) for dim in CLARITY_DIMENSIONS}))
    return components


def score_components(text: str, *, agents: list[str] | None = None) -> list[dict[str, Any]]:
    """Decompose the task into components and score each (one extra agent call, mock-safe).

    Returns components sorted by ambiguity (vaguest first), each with per-dimension scores,
    coverage-weighted overall, and weakest dimension.
    """
    text = (text or "").strip()
    if not text:
        return []

    from agent_lab.agents.registry import _mock_agents_enabled

    raw: list[tuple[str, dict[str, float]]]
    if _mock_agents_enabled():
        raw = [(name, _mock_dimension_scores(part)) for name, part in _mock_split_components(text)]
    else:
        from agent_lab.agents.registry import available_agents, call_agent

        panel = list(agents if agents is not None else available_agents())[:1]  # exactly one extra call
        reply = ""
        if panel:
            try:
                reply = call_agent(panel[0], _TOPOLOGY_SYSTEM, f"Task:\n{text}\n\nComponents:")
            except Exception:  # noqa: BLE001 - a flaky decomposer must not strand CLARIFY
                reply = ""
        raw = _parse_topology_reply(reply) or [("overall", {dim: 0.8 for dim in CLARITY_DIMENSIONS})]

    components: list[dict[str, Any]] = []
    for index, (name, dims) in enumerate(raw):
        overall = _coverage_weighted_overall(dims)
        weakest = max(dims, key=lambda d: dims[d]) if dims else None
        if weakest is not None and dims.get(weakest, 0.0) <= 0.0:
            weakest = None
        components.append(
            {
                "id": f"c{index + 1}",
                "name": name,
                "dimensions": dims,
                "overall": overall,
                "weakest_dimension": weakest,
            }
        )
    components.sort(key=lambda comp: comp["overall"], reverse=True)
    return components


def _attach_topology(result: dict[str, Any], text: str, agents: list[str] | None) -> dict[str, Any]:
    """When topology is enabled, attach component decomposition + the vaguest component."""
    if not topology_enabled():
        return result
    components = score_components(text, agents=agents)
    result["components"] = components
    result["weakest_component"] = components[0]["id"] if components else None
    return result


def score_clarity(text: str, *, agents: list[str] | None = None) -> dict[str, Any]:
    """Multi-agent lateral panel score. Returns dimensions + coverage-weighted overall.

    Mock-safe: anchored => all 0.0; empty => all 1.0; otherwise a deterministic per-dimension
    heuristic under mock, or one call per panelist live.
    """
    text = (text or "").strip()
    if not text:
        return _build_result({dim: 1.0 for dim in CLARITY_DIMENSIONS}, {})
    if detect_concrete_anchors(text):
        return _build_result({dim: 0.0 for dim in CLARITY_DIMENSIONS}, {})

    from agent_lab.agents.registry import _mock_agents_enabled

    if _mock_agents_enabled():
        return _attach_topology(_build_result(_mock_dimension_scores(text), {}), text, agents)

    from agent_lab.agents.registry import available_agents, call_agent

    panel = list(agents if agents is not None else available_agents())[:_MAX_PANEL]
    if not panel:
        return _attach_topology(_build_result({dim: 0.8 for dim in CLARITY_DIMENSIONS}, {}), text, agents)

    per_agent: dict[str, dict[str, float]] = {}
    user = f"Task:\n{text}\n\nPer-dimension ambiguity score:"
    for agent in panel:
        try:
            reply = call_agent(agent, _PANEL_SYSTEM, user)
        except Exception:  # noqa: BLE001 - a flaky panelist must not strand CLARIFY
            reply = ""
        parsed = _parse_dimension_reply(reply)
        # missing dimension => conservative (vague)
        per_agent[str(agent)] = {dim: parsed.get(dim, 0.8) for dim in CLARITY_DIMENSIONS}

    dimensions = {
        dim: round(sum(per_agent[a][dim] for a in per_agent) / len(per_agent), 4) for dim in CLARITY_DIMENSIONS
    }
    return _attach_topology(_build_result(dimensions, per_agent), text, agents)


def score_ambiguity(text: str) -> float:
    """Overall ambiguity in [0,1] (coverage-weighted weakest of the panel). Backward compatible."""
    return float(score_clarity(text)["overall"])


def lateral_questions_from_result(result: dict[str, Any], *, max_q: int = 3) -> list[dict[str, str]]:
    """Dimension-targeted clarifying questions from an already-computed ``score_clarity`` result.

    One-pass: callers that already hold a ``score_clarity`` result derive questions here
    instead of re-scoring. With topology on, questions target the vaguest *component* first
    (one question per component, on that component's weakest dimension); otherwise one question
    per global dimension above threshold. Capped at ``max_q``. Ordering matches the historical
    ``lateral_questions`` behavior.
    """
    threshold = _threshold()
    components = result.get("components")
    if components:
        questions: list[dict[str, str]] = []
        for comp in components:  # already sorted vaguest-first
            if float(comp.get("overall", 0.0)) <= threshold:
                continue
            dims = comp.get("dimensions") or {}
            ranked = sorted(CLARITY_DIMENSIONS, key=lambda d: dims.get(d, 0.0), reverse=True)
            for dim in ranked:
                if dims.get(dim, 0.0) <= threshold:
                    continue
                name = str(comp.get("name") or comp.get("id"))
                questions.append(
                    {
                        "id": f"clarify_{comp.get('id')}_{dim}",
                        "category": dim,
                        "component": name,
                        "prompt": f"[{name}] {_DIMENSION_QUESTIONS[dim]}",
                    }
                )
                break  # one question per component (its weakest dimension)
            if len(questions) >= max_q:
                break
        if questions:
            return questions[:max_q]
        # no component above threshold => fall through to the global view

    dimensions: dict[str, float] = result["dimensions"]
    ranked = sorted(CLARITY_DIMENSIONS, key=lambda d: dimensions.get(d, 0.0), reverse=True)
    questions = []
    for dim in ranked:
        if dimensions.get(dim, 0.0) <= threshold:
            continue
        questions.append({"id": f"clarify_{dim}", "category": dim, "prompt": _DIMENSION_QUESTIONS[dim]})
        if len(questions) >= max_q:
            break
    return questions


def lateral_questions(text: str, *, agents: list[str] | None = None, max_q: int = 3) -> list[dict[str, str]]:
    """Dimension-targeted clarifying questions, ordered by ambiguity (weakest first).

    Scores once via ``score_clarity`` then delegates to ``lateral_questions_from_result`` so
    there is no double scoring. With topology on, questions target the vaguest *component*
    first; otherwise one question per global dimension above threshold. Capped at ``max_q``.
    """
    result = score_clarity(text, agents=agents)
    return lateral_questions_from_result(result, max_q=max_q)


def record_clarity_panel(folder: Any, result: dict[str, Any]) -> None:
    """Persist the latest panel score to run.json mission_loop.clarity (observability)."""
    from pathlib import Path

    from agent_lab.run.meta import patch_run_meta

    def _record(run: dict[str, Any]) -> dict[str, Any]:
        ml = run.get("mission_loop")
        ml = ml if isinstance(ml, dict) else {}
        ml["clarity"] = {
            "overall": result.get("overall"),
            "dimensions": result.get("dimensions"),
            "weakest": result.get("weakest"),
            "panel": result.get("panel"),
            "components": result.get("components"),
            "weakest_component": result.get("weakest_component"),
            "at": _now_iso(),
        }
        run["mission_loop"] = ml
        return run

    patch_run_meta(Path(folder), _record)


def ensure_clarify_questions(folder: Any) -> dict[str, Any] | None:
    """Real question loop: when CLARIFY is still ambiguous, generate dimension-targeted
    clarifying questions and persist them through ``session_clarifier`` for the human.

    Idempotent: an open (non-complete) interview is left as-is so answers can land.
    """
    from pathlib import Path

    from agent_lab.run.meta import read_run_meta
    from agent_lab.session.clarifier import (
        get_clarifier_interview,
        persist_clarifier_interview,
        public_clarifier_interview,
    )

    path = Path(folder)
    run = read_run_meta(path)
    existing = get_clarifier_interview(run)
    if isinstance(existing, dict) and existing.get("status") != "complete":
        return public_clarifier_interview(run)

    text = _mission_clarity_text(run)
    result = score_clarity(text)
    record_clarity_panel(path, result)
    questions = lateral_questions(text)
    if not questions:
        return None
    interview: dict[str, Any] = {
        "version": 2,
        "plan_mode": False,
        "status": "pending",
        "source": "clarify_panel",
        "human_turn": 0,
        "questions": questions[:5],
        "answers": {},
        "weakest": result.get("weakest"),
        "created_at": _now_iso(),
    }
    persist_clarifier_interview(path, interview)
    return public_clarifier_interview(read_run_meta(path))


def clarity_threshold_met(run: dict[str, Any]) -> bool:
    """CLARIFY may pass to DISCUSS when concrete anchors exist OR overall ambiguity <= threshold.

    Answered clarifier Q&A is folded into the scored text, so completing the question loop
    advances the mission.
    """
    text = _mission_clarity_text(run)
    if detect_concrete_anchors(text):
        return True
    return score_ambiguity(text) <= _threshold()


def established_facts(run: dict[str, Any]) -> list[dict[str, Any]]:
    """Confirmed clarify facts from run.json mission_loop.clarity.facts."""
    ml = run.get("mission_loop") if isinstance(run, dict) else None
    clarity = ml.get("clarity") if isinstance(ml, dict) else None
    facts = clarity.get("facts") if isinstance(clarity, dict) else None
    return [f for f in facts if isinstance(f, dict)] if isinstance(facts, list) else []


def extract_established_facts(folder: Any) -> list[dict[str, Any]]:
    """Harvest answered clarifier Q&A into durable mission_loop.clarity.facts.

    Idempotent: keyed by question id, so re-running merges/updates rather than duplicating.
    These confirmed facts are injected into DISCUSS/plan context (see ``format_facts_block``)
    so the Room never re-asks what the human already answered.
    """
    from pathlib import Path

    from agent_lab.run.meta import patch_run_meta, read_run_meta
    from agent_lab.session.clarifier import get_clarifier_interview

    path = Path(folder)
    run = read_run_meta(path)
    interview = get_clarifier_interview(run)
    if not isinstance(interview, dict):
        return established_facts(run)
    answers = interview.get("answers") if isinstance(interview.get("answers"), dict) else {}
    new_facts: list[dict[str, Any]] = []
    for question in interview.get("questions") or []:
        if not isinstance(question, dict):
            continue
        qid = str(question.get("id") or "")
        answer = str(answers.get(qid, "") or "").strip()
        if not qid or not answer:
            continue
        new_facts.append(
            {
                "id": qid,
                "category": question.get("category"),
                "component": question.get("component"),
                "question": str(question.get("prompt") or ""),
                "answer": answer,
                "fact": answer,
                "at": _now_iso(),
            }
        )
    if not new_facts:
        return established_facts(run)

    def _merge(run_in: dict[str, Any]) -> dict[str, Any]:
        ml = run_in.get("mission_loop")
        ml = ml if isinstance(ml, dict) else {}
        clarity = ml.get("clarity")
        clarity = clarity if isinstance(clarity, dict) else {}
        existing = clarity.get("facts")
        existing = existing if isinstance(existing, list) else []
        merged: dict[str, dict[str, Any]] = {}
        for fact in existing:
            if isinstance(fact, dict) and fact.get("id"):
                merged[str(fact["id"])] = fact
        for fact in new_facts:
            merged[fact["id"]] = fact
        clarity["facts"] = list(merged.values())[:50]
        ml["clarity"] = clarity
        run_in["mission_loop"] = ml
        return run_in

    patch_run_meta(path, _merge)
    return established_facts(read_run_meta(path))


def format_facts_block(run: dict[str, Any]) -> str:
    """Render confirmed clarify facts for injection into the DISCUSS/plan constraints block."""
    facts = established_facts(run)
    if not facts:
        return ""
    lines = ["[확정 사실 · clarify]"]
    for fact in facts[:12]:
        answer = str(fact.get("answer") or fact.get("fact") or "").strip()
        if not answer:
            continue
        component = str(fact.get("component") or "").strip()
        category = str(fact.get("category") or "").strip()
        tag = f"{component}/{category}" if component else category
        prefix = f"[{tag}] " if tag else ""
        lines.append(f"- {prefix}{answer}")
    return "\n".join(lines).strip() if len(lines) > 1 else ""
