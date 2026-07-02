"""S2 foundation — episode-based roster hints (not global task-type bandit).

S2 does **not** learn "optimal agent combo per task category". Static
topic_router labels are routing hints only; sparse data cannot support
convergence. This module maps a **known role combo** to a subset hint for
feedback_advisor; ε-greedy explore stays session-local (S1.5).

Full promote/demote ships only after S1 dogfood accumulates enough W2 samples.
"""

from __future__ import annotations


def subset_from_role_combo(
    combo_roles: dict[str, str],
    available_agents: list[str],
) -> tuple[str, ...]:
    """Map a winning role combo to an agent subset hint (stable order)."""
    pool = [str(a).strip().lower() for a in available_agents if str(a).strip()]
    if not combo_roles or not pool:
        return ()
    ordered = [a for a in pool if a in combo_roles]
    return tuple(ordered) if len(ordered) >= 2 else ()
