"""S2 foundation — runtime role-combo bandit interface (Phase 4).

Full ε-greedy promote/demote agent pool ships after S1 loop closure.
Today: subset_from_role_combo feeds feedback_advisor.suggested_subset hints.
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
