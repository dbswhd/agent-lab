"""LLM-as-judge trajectory quality eval (G8).

Adds a *semantic* quality layer on top of the structural offline KPIs in
``session_score`` — rubric-scores a session's transcript/plan/goal and combines
the result with the real cost (``cost_ledger``, G1) to expose quality-per-dollar.

Mirrors the live opt-in pattern of ``oracle_core``: judging is OFF unless
``AGENT_LAB_JUDGE_LIVE`` is set (or a ``judge_call`` is injected for tests), so
the default mock CI path never calls an LLM and ``score_session`` stays
deterministic. Every entry point is defensive — judging must never break scoring.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Callable

_TRUE = frozenset({"1", "true", "yes", "on"})

# 1–5 rubric dimensions.
DEFAULT_RUBRIC: tuple[str, ...] = (
    "goal_fit",
    "correctness",
    "completeness",
    "clarity",
    "efficiency",
)
_MAX_TRANSCRIPT_CHARS = 16_000


def judge_live_enabled() -> bool:
    """Live judge opt-in via ``AGENT_LAB_JUDGE_LIVE``."""
    return os.getenv("AGENT_LAB_JUDGE_LIVE", "").strip().lower() in _TRUE


def _judge_model() -> str | None:
    return (os.getenv("AGENT_LAB_JUDGE_MODEL") or "").strip() or None


def build_judge_prompt(
    goal: str,
    plan_md: str,
    transcript: str,
    rubric: tuple[str, ...] = DEFAULT_RUBRIC,
) -> str:
    dims = ", ".join(rubric)
    schema = ", ".join(f'"{d}": <1-5>' for d in rubric)
    return (
        "You are an impartial evaluator of a multi-agent coding session. Score the "
        "OUTCOME quality against the goal using the rubric. Be strict and concrete.\n\n"
        f"Rubric dimensions (integer 1=poor .. 5=excellent): {dims}\n\n"
        f"## Goal\n{goal or '(none stated)'}\n\n"
        f"## Final plan\n{plan_md or '(no plan.md)'}\n\n"
        f"## Transcript (trimmed)\n{transcript or '(empty)'}\n\n"
        "Reply with ONLY a JSON object, no prose:\n"
        f'{{"scores": {{{schema}}}, "overall": <1-5 float>, '
        '"verdict": "pass"|"fail", "rationale": "<=2 sentences"}'
    )


def _clamp_score(value: Any) -> int | None:
    try:
        n = int(round(float(value)))
    except (TypeError, ValueError):
        return None
    return max(1, min(5, n))


def _extract_json(text: str) -> dict[str, Any] | None:
    # First balanced-looking {...} block.
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        obj = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


def parse_judge_response(
    raw: str,
    rubric: tuple[str, ...] = DEFAULT_RUBRIC,
) -> dict[str, Any]:
    """Parse judge output (JSON-first, conservative fallback)."""
    text = str(raw or "").strip()
    if not text:
        return {"scores": {}, "overall": None, "verdict": "fail", "rationale": "empty judge response"}

    scores: dict[str, int] = {}
    rationale = ""
    overall: float | None = None
    verdict: str | None = None

    obj = _extract_json(text)
    if obj is not None:
        raw_scores = obj.get("scores") if isinstance(obj.get("scores"), dict) else {}
        for dim in rubric:
            val = _clamp_score(raw_scores.get(dim))
            if val is not None:
                scores[dim] = val
        if obj.get("overall") is not None:
            try:
                overall = max(1.0, min(5.0, float(obj["overall"])))
            except (TypeError, ValueError):
                overall = None
        v = str(obj.get("verdict") or "").strip().lower()
        if v in ("pass", "fail"):
            verdict = v
        rationale = str(obj.get("rationale") or "")[:500]

    # Fallback: regex on free text.
    if overall is None:
        m = re.search(r"overall[\"']?\s*[:=]\s*([0-9](?:\.[0-9])?)", text, re.IGNORECASE)
        if m:
            try:
                overall = max(1.0, min(5.0, float(m.group(1))))
            except ValueError:
                overall = None
    if overall is None and scores:
        overall = round(sum(scores.values()) / len(scores), 2)
    if verdict is None:
        upper = text.upper()
        if re.search(r"\bVERDICT[\"']?\s*[:=]\s*PASS\b", upper) or upper.startswith("PASS"):
            verdict = "pass"
        elif overall is not None:
            verdict = "pass" if overall >= 3.0 else "fail"
        else:
            verdict = "fail"
    if not rationale:
        rationale = text[:500]

    return {"scores": scores, "overall": overall, "verdict": verdict, "rationale": rationale}


def invoke_judge(
    prompt: str,
    *,
    judge_call: Callable[[str], str] | None = None,
) -> tuple[str, str]:
    """Return (raw_response, source). ``judge_call`` injects a fake LLM for tests."""
    if judge_call is not None:
        return str(judge_call(prompt) or "").strip(), "live"
    if judge_live_enabled():
        from agent_lab import claude_cli

        model = _judge_model()
        if model:
            os.environ.setdefault("CLAUDE_SCRIBE_MODEL", model)
        raw = claude_cli.invoke("judge", prompt, scribe=True)
        return str(raw or "").strip(), "live"
    return "", "mock"


def _goal_text(folder: Path, run_meta: dict[str, Any]) -> str:
    loop = run_meta.get("verified_loop") if isinstance(run_meta.get("verified_loop"), dict) else {}
    goal = loop.get("goal")
    if isinstance(goal, dict):
        goal = goal.get("text") or goal.get("goal")
    if isinstance(goal, str) and goal.strip():
        return goal.strip()
    topic = folder / "topic.txt"
    if topic.is_file():
        return topic.read_text(encoding="utf-8").strip()
    return ""


def _build_transcript(messages: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for m in messages:
        role = str(m.get("role") or "")
        who = str(m.get("agent") or role)
        content = str(m.get("content") or "").strip()
        if content:
            parts.append(f"[{who}] {content}")
    text = "\n\n".join(parts)
    if len(text) <= _MAX_TRANSCRIPT_CHARS:
        return text
    head = text[:4_000]
    tail = text[-(_MAX_TRANSCRIPT_CHARS - 4_000):]
    return f"{head}\n\n…(trimmed)…\n\n{tail}"


def _cumulative_usd(run_meta: dict[str, Any]) -> float:
    ledger = run_meta.get("cost_ledger")
    if isinstance(ledger, dict):
        cumulative = ledger.get("cumulative")
        if isinstance(cumulative, dict):
            return float(cumulative.get("usd", 0.0) or 0.0)
    return 0.0


def judge_session(
    folder: Path,
    *,
    run_meta: dict[str, Any] | None = None,
    messages: list[dict[str, Any]] | None = None,
    judge_call: Callable[[str], str] | None = None,
) -> dict[str, Any]:
    """Rubric-score a session (opt-in). Returns ``{enabled: False}`` when off.

    Never raises — any failure degrades to a disabled block so scoring proceeds.
    """
    try:
        if judge_call is None and not judge_live_enabled():
            return {"enabled": False, "reason": "AGENT_LAB_JUDGE_LIVE off"}
        if run_meta is None:
            from agent_lab.run_meta import read_run_meta

            run_meta = read_run_meta(folder)
        if messages is None:
            from agent_lab.session_score import _load_chat_messages

            messages = _load_chat_messages(folder)
        plan_path = folder / "plan.md"
        plan_md = plan_path.read_text(encoding="utf-8") if plan_path.is_file() else ""
        prompt = build_judge_prompt(
            _goal_text(folder, run_meta),
            plan_md,
            _build_transcript(messages),
        )
        raw, source = invoke_judge(prompt, judge_call=judge_call)
        parsed = parse_judge_response(raw)
        usd = _cumulative_usd(run_meta)
        overall = parsed.get("overall")
        usd_per_point = (
            round(usd / overall, 6) if isinstance(overall, (int, float)) and overall > 0 else None
        )
        return {
            "enabled": True,
            "source": source,
            **parsed,
            "cost": {"usd": round(usd, 6), "usd_per_point": usd_per_point},
        }
    except Exception as exc:  # judging must never break scoring
        return {"enabled": False, "reason": f"judge error: {exc}"[:200]}
