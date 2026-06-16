"""Default model IDs for 3-agent room (override via env)."""

from __future__ import annotations

DEFAULT_CURSOR_MODEL = "default"
DEFAULT_CODEX_MODEL = "gpt-5.5"
DEFAULT_CODEX_REASONING_EFFORT = "high"
DEFAULT_CODEX_ROOM_REASONING_EFFORT = "high"
DEFAULT_CODEX_ROOM_MAX_COMMANDS = 6
# Abandon a silently-hung room agent after this much inactivity (was 600s/10min,
# which felt like an infinite wait when Codex stalled on a usage limit).
DEFAULT_CODEX_ROOM_IDLE_TIMEOUT_SEC = 180
# Hard wall-clock cap for a single room turn. Without this, a rate-limited Codex
# that keeps emitting "retrying" events resets the idle timer and never stops.
DEFAULT_CODEX_ROOM_TIMEOUT_SEC = 300
DEFAULT_CLAUDE_MODEL = "opus"
DEFAULT_CLAUDE_REASONING_EFFORT = "high"

# --- Cost estimation (G1 economics) ---------------------------------------
# Approximate public list prices in USD per 1M tokens. Used ONLY as a fallback
# when a bridge does not report an authoritative ``total_cost_usd`` (Claude Code
# CLI does report it, so its numbers are trusted as-is). Keyed by a substring of
# the normalized model id; first match wins. Override-friendly: extend the dict.
# (input, output, cache_read) — cache_read defaults to 10% of input when omitted.
MODEL_PRICE_PER_MTOK: dict[str, tuple[float, float, float]] = {
    "opus": (15.0, 75.0, 1.5),
    "sonnet": (3.0, 15.0, 0.3),
    "haiku": (0.80, 4.0, 0.08),
    "gpt-5": (1.25, 10.0, 0.125),
    "gpt-4": (2.50, 10.0, 0.25),
    "o3": (2.0, 8.0, 0.2),
}
# Used when no table entry matches; conservative mid-tier estimate.
DEFAULT_PRICE_PER_MTOK: tuple[float, float, float] = (3.0, 15.0, 0.3)


def _price_for(model: str | None) -> tuple[float, float, float]:
    name = (model or "").strip().lower()
    for key, price in MODEL_PRICE_PER_MTOK.items():
        if key in name:
            return price
    return DEFAULT_PRICE_PER_MTOK


def estimate_cost_usd(
    model: str | None,
    *,
    tokens_in: int = 0,
    tokens_out: int = 0,
    cache_read: int = 0,
) -> float:
    """Estimate request cost in USD from token counts (fallback only).

    ``cache_read`` tokens are billed at the cheaper cache-read rate and are
    treated as a subset of ``tokens_in`` (so non-cached input = in - cache_read).
    """
    in_rate, out_rate, cache_rate = _price_for(model)
    fresh_in = max(0, int(tokens_in) - int(cache_read))
    cost = (
        fresh_in * in_rate
        + int(cache_read) * cache_rate
        + int(tokens_out) * out_rate
    ) / 1_000_000.0
    return round(cost, 6)
