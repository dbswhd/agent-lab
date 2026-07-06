"""Shared topic route → capability seed → subset → role plan wiring for all turn paths."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agent_lab.run.state import RunStateLike

from agent_lab.topic_router import CategoryRoute, enrich_route_with_role_plan, resolve_active_subset, resolve_topic_route


@dataclass(frozen=True, slots=True)
class TurnRoutingResult:
    route: CategoryRoute
    active: list[str]
    hint: Any


def bootstrap_turn_route(
    topic: str,
    run_meta: RunStateLike,
    *,
    efficiency_mode: bool = False,
) -> CategoryRoute:
    """Resolve route, stamp topology, seed capabilities."""
    route = resolve_topic_route(
        topic,
        turn_profile=str(run_meta.get("turn_profile") or ""),
        session_template=str(run_meta.get("session_template") or ""),
        efficiency_mode=efficiency_mode,
    )
    from agent_lab.run.meta import stamp_run_meta

    stamp_run_meta(run_meta, _turn_topology=route.topology)
    from agent_lab.room.agent_capabilities import seed_capabilities_for_route

    seed_capabilities_for_route(route, run_meta)
    return route


def apply_turn_role_plan(
    route: CategoryRoute,
    run_meta: RunStateLike,
    active: list[str],
    *,
    topic: str,
    hint: Any | None = None,
) -> CategoryRoute:
    """Persist _turn_category + _turn_roles from route (after active list is final)."""
    from agent_lab.feedback_advisor import SetupHint, advise_setup
    from agent_lab.role_plan import apply_preset_role_overrides, resolve_role_plan
    from agent_lab.room.preset import resolve_role_policy

    if hint is None:
        _room_preset = str(run_meta.get("room_preset") or "").strip().lower()
        hint = advise_setup(
            topic,
            route.category,
            active,
            room_preset=_room_preset,
        )
    _role_policy = resolve_role_policy(run_meta)
    route = enrich_route_with_role_plan(route, active, hint=hint, policy=_role_policy)
    cat_dict = route.category_dict()
    if getattr(hint, "source", "") in ("history", "explore"):
        cat_dict["advisor_rationale"] = hint.rationale
        cat_dict["advisor_source"] = hint.source
        cat_dict["advisor_combo_id"] = getattr(hint, "combo_id", "") or ""
    from agent_lab.run.meta import stamp_run_meta

    stamp_run_meta(
        run_meta,
        _turn_category=cat_dict,
        role_policy=_role_policy,
        _turn_roles=apply_preset_role_overrides(
            run_meta,
            resolve_role_plan(
                route=route,
                agents=active,
                hint=hint,
                policy=_role_policy,
            ),
            active,
        ),
    )
    return route


def finalize_turn_routing(
    route: CategoryRoute,
    run_meta: RunStateLike,
    active: list[str],
    *,
    topic: str,
    agents: list[str] | None = None,
    min_agents: int = 2,
    apply_subset: bool = True,
    on_event: Any | None = None,
    hint: Any | None = None,
) -> TurnRoutingResult:
    """Expert pool subset (optional) + role plan for the current active roster."""
    from agent_lab.feedback_advisor import SetupHint, advise_setup

    pool = [str(a).strip().lower() for a in active if str(a).strip()]
    if hint is None:
        _room_preset = str(run_meta.get("room_preset") or "").strip().lower()
        hint = advise_setup(topic, route.category, pool, room_preset=_room_preset)

    if apply_subset:
        user_selected_multi = agents is not None and len([a for a in agents if str(a).strip()]) >= 2
        filtered, applied_subset = resolve_active_subset(route, pool, hint=hint, min_agents=min_agents)
        if applied_subset and not (user_selected_multi and len(filtered) < len(pool)):
            pool = [str(a).strip().lower() for a in filtered if str(a).strip()]
            if on_event:
                on_event(
                    "agent_subset_applied",
                    {
                        "subset": list(applied_subset),
                        "active": pool,
                        "task_type": route.task_type,
                        "category": route.category,
                        "message": (
                            f"Expert Pool — {route.task_type} 작업으로 감지: "
                            f"{', '.join(pool)} 우선 참여."
                        ),
                    },
                )

    route = apply_turn_role_plan(route, run_meta, pool, topic=topic, hint=hint)
    return TurnRoutingResult(route=route, active=pool, hint=hint)


def prepare_turn_routing(
    topic: str,
    run_meta: RunStateLike,
    active: list[str],
    *,
    agents: list[str] | None = None,
    efficiency_mode: bool = False,
    min_agents: int = 2,
    apply_subset: bool = True,
    on_event: Any | None = None,
) -> TurnRoutingResult:
    """Full bootstrap + finalize — use from parallel (non-consensus) turns."""
    route = bootstrap_turn_route(topic, run_meta, efficiency_mode=efficiency_mode)
    return finalize_turn_routing(
        route,
        run_meta,
        active,
        topic=topic,
        agents=agents,
        min_agents=min_agents,
        apply_subset=apply_subset,
        on_event=on_event,
    )


def refresh_routing_after_escalation(
    route: CategoryRoute,
    run_meta: RunStateLike,
    active: list[str],
    *,
    topic: str,
) -> CategoryRoute:
    """Re-seed capabilities and role plan for escalated category (subset already released)."""
    from agent_lab.run.meta import stamp_run_meta

    stamp_run_meta(run_meta, _turn_topology=route.topology)
    from agent_lab.room.agent_capabilities import seed_capabilities_for_route

    seed_capabilities_for_route(route, run_meta)
    return apply_turn_role_plan(route, run_meta, active, topic=topic, hint=None)
