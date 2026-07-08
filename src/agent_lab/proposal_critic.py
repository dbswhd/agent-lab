"""Proposal thesis critic — deterministic + optional live Critic (Tier 1 MCP)."""

from __future__ import annotations

import json
import re
from typing import Any

from agent_lab.env_flags import env_bool
from agent_lab.pipeline_research_read import get_strategy_verdict

_BLOCKED_THESIS = (
    "ignore previous",
    "bypass risk",
    "override risk",
    "disable guard",
    "place this live order",
)
_MIN_THESIS_LEN = 12
_VAGUE_PATTERNS = (
    re.compile(r"\b(maybe|perhaps|guess|probably|might)\b", re.I),
    re.compile(r"\b(좋을\s*것|아마|추정|감으로)\b"),
)


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def _parse_quote(quote_json: Any) -> dict[str, Any]:
    if quote_json is None or quote_json == "":
        return {}
    if isinstance(quote_json, dict):
        return quote_json
    if isinstance(quote_json, str):
        try:
            loaded = json.loads(quote_json)
        except json.JSONDecodeError:
            return {}
        return loaded if isinstance(loaded, dict) else {}
    return {}


def _verdict_cap(verdict_payload: dict[str, Any]) -> tuple[float, list[str], list[str]]:
    objections: list[str] = []
    missing: list[str] = []
    if not verdict_payload.get("ok"):
        missing.append("backtest_ref_not_resolved")
        return 0.35, objections, missing

    verdict = str(verdict_payload.get("verdict") or "").upper()
    eligible = bool(verdict_payload.get("eligible_for_proposal"))
    if verdict == "FAIL" or not eligible:
        objections.append(f"backtest verdict {verdict or 'FAIL'} — not eligible for proposal")
        return 0.0, objections, missing

    if verdict in {"INFO", "UNKNOWN", ""}:
        objections.append(f"backtest verdict {verdict or 'UNKNOWN'} — weak evidence")
        return 0.4, objections, missing

    sharpe = verdict_payload.get("oos_sharpe")
    try:
        sharpe_f = float(sharpe) if sharpe is not None else 1.0
    except (TypeError, ValueError):
        sharpe_f = 1.0
    cap = _clamp(0.55 + sharpe_f * 0.08, 0.5, 0.95)
    fails = verdict_payload.get("fails") or []
    if fails:
        objections.append(f"card fails: {fails[0]}")
        cap = min(cap, 0.45)
    return round(cap, 4), objections, missing


def _thesis_checks(thesis: str) -> tuple[list[str], list[str]]:
    objections: list[str] = []
    missing: list[str] = []
    text = (thesis or "").strip()
    if len(text) < _MIN_THESIS_LEN:
        objections.append("thesis too short — need concrete trigger and sizing rationale")
    lowered = text.lower()
    for phrase in _BLOCKED_THESIS:
        if phrase in lowered:
            objections.append(f"blocked phrase in thesis: {phrase}")
    if text and not re.search(r"[0-9%]", text):
        missing.append("numeric evidence (price, size, %, or signal metric)")
    for pattern in _VAGUE_PATTERNS:
        if pattern.search(text):
            objections.append("thesis language too vague — cite signal/overlay evidence")
            break
    if not text:
        missing.append("thesis text")
    return objections, missing


def _quote_checks(quote: dict[str, Any], symbol: str | None) -> tuple[list[str], list[str]]:
    objections: list[str] = []
    missing: list[str] = []
    if not quote:
        missing.append("quote_snapshot")
        return objections, missing
    if quote.get("ok") is False:
        objections.append(f"quote unavailable: {quote.get('reason') or 'error'}")
        return objections, missing
    price = quote.get("price")
    if price is None:
        missing.append("quote.price")
    sym = str(quote.get("symbol") or "").strip()
    if symbol and sym and sym != symbol.strip().upper():
        objections.append(f"quote symbol mismatch ({sym} vs {symbol})")
    return objections, missing


def _freshness_checks(quote: dict[str, Any]) -> list[str]:
    freshness = quote.get("freshness")
    if not isinstance(freshness, dict):
        return []
    if freshness.get("blocking"):
        return ["data freshness blocking — do not propose live rebalance"]
    return []


def mock_critic_note(
    *,
    thesis: str,
    ref: str,
    verdict_payload: dict[str, Any],
    quote: dict[str, Any],
) -> str:
    """Fixture-safe extra note (no LLM)."""
    _ = ref
    if str(verdict_payload.get("verdict") or "").upper() == "FAIL":
        return "FAIL backtest ref — abandon or replace ref before ingest."
    if len((thesis or "").strip()) < _MIN_THESIS_LEN:
        return "Expand thesis with overlay signal + sizing rationale."
    if quote and quote.get("ok") is False:
        return "Quote missing — add price check before notional sizing."
    return ""


def _live_critic_prompt(
    *,
    thesis: str,
    ref: str,
    verdict_payload: dict[str, Any],
    quote: dict[str, Any],
    agent_confidence: float | None,
) -> str:
    verdict_json = json.dumps(
        {
            "verdict": verdict_payload.get("verdict"),
            "eligible": verdict_payload.get("eligible_for_proposal"),
            "oos_sharpe": verdict_payload.get("oos_sharpe"),
            "fails": (verdict_payload.get("fails") or [])[:3],
        },
        ensure_ascii=False,
    )
    quote_json = json.dumps(
        {k: quote.get(k) for k in ("symbol", "price", "change_pct", "ok", "source") if k in quote},
        ensure_ascii=False,
    )
    conf = "" if agent_confidence is None else f"{agent_confidence:.2f}"
    return (
        "Review this trade proposal thesis for a quant desk (read-only, no orders).\n\n"
        f"thesis: {thesis.strip()[:500]}\n"
        f"backtest_ref: {ref}\n"
        f"verdict: {verdict_json}\n"
        f"quote: {quote_json}\n"
        f"agent_confidence: {conf}\n\n"
        "Reply with JSON only:\n"
        '{"objections":["..."],"missing_evidence":["..."],"confidence_cap":0.0}\n'
        "Rules: max 3 objections; FAIL verdict → confidence_cap=0; be concise."
    )


def _parse_live_critic(raw: str) -> dict[str, Any] | None:
    text = (raw or "").strip()
    if not text:
        return None
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def apply_confidence_cap(agent_confidence: float, review: dict[str, Any]) -> float:
    """Merge agent confidence with critic confidence_cap."""
    try:
        base = float(agent_confidence)
    except (TypeError, ValueError):
        base = 0.0
    base = _clamp(base)
    try:
        cap = float(review.get("confidence_cap", base))
    except (TypeError, ValueError):
        cap = base
    return round(min(base, _clamp(cap)), 4)


def review_proposal_thesis(
    thesis: str,
    ref: str,
    quote_json: Any = None,
    *,
    symbol: str | None = None,
    agent_confidence: float | None = None,
    critic_call: Any = None,
) -> dict[str, Any]:
    """
    Critic review for one proposal draft.

    Returns objections, confidence_cap, missing_evidence, needs_human.
    """
    backtest_ref = (ref or "").strip()
    verdict_payload = get_strategy_verdict(backtest_ref) if backtest_ref else {"ok": False}
    quote = _parse_quote(quote_json)

    objections: list[str] = []
    missing: list[str] = []

    if not backtest_ref:
        missing.append("backtest_ref")

    cap, v_obj, v_miss = _verdict_cap(verdict_payload)
    objections.extend(v_obj)
    missing.extend(v_miss)

    t_obj, t_miss = _thesis_checks(thesis)
    objections.extend(t_obj)
    missing.extend(t_miss)

    q_obj, q_miss = _quote_checks(quote, symbol)
    objections.extend(q_obj)
    missing.extend(q_miss)
    objections.extend(_freshness_checks(quote))

    source = "deterministic"
    if critic_call is not None:
        raw = critic_call(
            _live_critic_prompt(
                thesis=thesis,
                ref=backtest_ref,
                verdict_payload=verdict_payload,
                quote=quote,
                agent_confidence=agent_confidence,
            )
        )
        parsed = _parse_live_critic(str(raw or ""))
        source = "injected"
    elif env_bool("AGENT_LAB_RESEARCH_MCP_CRITIC_LIVE"):
        from agent_lab.claude import cli as claude_cli

        raw = claude_cli.invoke(
            "proposal-critic",
            _live_critic_prompt(
                thesis=thesis,
                ref=backtest_ref,
                verdict_payload=verdict_payload,
                quote=quote,
                agent_confidence=agent_confidence,
            ),
            scribe=True,
        )
        parsed = _parse_live_critic(str(raw or ""))
        source = "live"
    else:
        note = mock_critic_note(
            thesis=thesis,
            ref=backtest_ref,
            verdict_payload=verdict_payload,
            quote=quote,
        )
        parsed = None
        if note:
            objections.append(note)

    if parsed:
        extra_obj = parsed.get("objections")
        if isinstance(extra_obj, list):
            for item in extra_obj[:3]:
                text = str(item).strip()
                if text and text not in objections:
                    objections.append(text)
        extra_miss = parsed.get("missing_evidence")
        if isinstance(extra_miss, list):
            for item in extra_miss[:5]:
                text = str(item).strip()
                if text and text not in missing:
                    missing.append(text)
        try:
            live_cap = float(parsed.get("confidence_cap", cap))
            cap = min(cap, _clamp(live_cap))
        except (TypeError, ValueError):
            pass

    if agent_confidence is not None:
        cap = min(cap, _clamp(float(agent_confidence)))

    for _ in objections:
        cap = round(max(0.0, cap - 0.08), 4)

    needs_human = bool(objections) or bool(missing)

    return {
        "ok": True,
        "ref": backtest_ref,
        "objections": objections[:6],
        "missing_evidence": missing[:6],
        "confidence_cap": cap,
        "needs_human": needs_human,
        "source": source,
        "verdict": {
            "verdict": verdict_payload.get("verdict"),
            "eligible_for_proposal": verdict_payload.get("eligible_for_proposal"),
            "oos_sharpe": verdict_payload.get("oos_sharpe"),
        },
    }
