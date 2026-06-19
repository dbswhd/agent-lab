"""발산(divergence) turn-profile helpers.

Divergence is an additive discussion-phase mode: agents hold distinct
positions without premature consensus and the room returns a bounded list of
approach-distinct alternative options, then stops. No selection, no execute
linkage — the human chooses from the options list.
"""

from __future__ import annotations

from typing import Any

# Accept both the Korean label used in the UI and the ascii id.
DIVERGENCE_PROFILES = frozenset({"divergence", "발산"})

# Cap the options list so the seat returns a small, comparable set.
# (Lower bound is guidance for the agents, not enforced here — it depends on
# how many seats actually reply.)
MAX_DIVERGENCE_OPTIONS = 4


def is_divergence_profile(turn_profile: str | None) -> bool:
    """True when the turn profile selects divergence mode."""
    return (turn_profile or "").strip().lower() in DIVERGENCE_PROFILES


def _reply_field(reply: Any, *names: str) -> str:
    """Read the first non-empty attribute/key among ``names`` (duck-typed)."""
    for name in names:
        if isinstance(reply, dict):
            value = reply.get(name)
        else:
            value = getattr(reply, name, None)
        if value:
            return str(value)
    return ""


def format_divergence_options(replies: list[Any]) -> list[dict[str, str]]:
    """Format agent replies into a bounded list of approach-distinct options.

    One option per agent reply, capped at ``MAX_DIVERGENCE_OPTIONS``. The list
    is the terminal artifact of a divergence run: callers present it for human
    selection and MUST NOT auto-advance to execute. Distinctness of approaches
    is the human's judgement call, not enforced here.
    """
    options: list[dict[str, str]] = []
    for reply in replies:
        approach = _reply_field(reply, "content", "text", "message").strip()
        if not approach:
            continue
        options.append(
            {
                "index": str(len(options) + 1),
                "agent": _reply_field(reply, "agent", "role", "name"),
                "approach": approach,
            }
        )
        if len(options) >= MAX_DIVERGENCE_OPTIONS:
            break
    return options
