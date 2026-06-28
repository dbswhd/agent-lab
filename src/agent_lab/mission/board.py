"""Mission Board + turn budget — Paperclip task/budget without N-agent Room (MB-1, MB-2)."""

from __future__ import annotations

import os
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Callable, Literal

from agent_lab.plan.actions import find_dry_run_action, parse_plan_actions
from agent_lab.run.meta import patch_run_meta, read_run_meta

LaneId = Literal["discuss", "execute", "verify", "human"]

DEFAULT_DISCUSS_ROLES: tuple[str, ...] = ("cursor", "codex", "claude")

DEFAULT_TURN_BUDGET_CAPS: dict[str, Any] = {
    "agent_calls_per_human_turn": 9,
    "codex_shell_per_turn": None,
    "repairs_per_action": 2,
    "mission_iterations": 20,
    "autorun_ticks_per_hour": 60,
}

_DEFAULT_COUNTERS: dict[str, Any] = {
    "agent_calls_per_human_turn": 0,
    "codex_shell_per_turn": 0,
    "repairs_per_action": {},
    "mission_iterations": 0,
    "autorun_ticks_this_hour": 0,
    "autorun_tick_hour": None,
    "human_turn": 0,
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hour_bucket() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H")


def default_lane_roles() -> dict[str, Any]:
    return {
        "discuss": list(DEFAULT_DISCUSS_ROLES),
        "execute_default": "cursor",
        "repair_default": "codex",
        "verify_oracle": "mock",
    }


def default_mission_board() -> dict[str, Any]:
    return {
        "goal_chain": [],
        "checkout": None,
        "lane_roles": default_lane_roles(),
    }


def default_turn_budget() -> dict[str, Any]:
    caps = dict(DEFAULT_TURN_BUDGET_CAPS)
    codex_cap = os.getenv("CODEX_ROOM_MAX_COMMANDS", "").strip()
    if codex_cap.isdigit():
        caps["codex_shell_per_turn"] = int(codex_cap)
    return {
        "caps": caps,
        "counters": dict(_DEFAULT_COUNTERS),
        "budget_pct": 0,
        "overflow": None,
        "updated_at": None,
    }


def get_mission_board(run: dict[str, Any] | None) -> dict[str, Any]:
    raw = (run or {}).get("mission_board")
    base = default_mission_board()
    if not isinstance(raw, dict):
        return base
    merged = dict(base)
    if isinstance(raw.get("lane_roles"), dict):
        roles = dict(default_lane_roles())
        roles.update(raw["lane_roles"])
        discuss = roles.get("discuss")
        if isinstance(discuss, list) and discuss:
            roles["discuss"] = [str(a).strip().lower() for a in discuss if str(a).strip()] or list(
                DEFAULT_DISCUSS_ROLES
            )
        merged["lane_roles"] = roles
    if isinstance(raw.get("goal_chain"), list):
        merged["goal_chain"] = [item for item in raw["goal_chain"] if isinstance(item, dict)]
    checkout = raw.get("checkout")
    merged["checkout"] = checkout if isinstance(checkout, dict) else None
    return merged


def get_turn_budget(run: dict[str, Any] | None) -> dict[str, Any]:
    raw = (run or {}).get("turn_budget")
    base = default_turn_budget()
    if not isinstance(raw, dict):
        return base
    caps = dict(base["caps"])
    if isinstance(raw.get("caps"), dict):
        caps.update(raw["caps"])
    counters = dict(_DEFAULT_COUNTERS)
    if isinstance(raw.get("counters"), dict):
        counters.update(raw["counters"])
        repairs = raw["counters"].get("repairs_per_action")
        if isinstance(repairs, dict):
            counters["repairs_per_action"] = dict(repairs)
    return {
        "caps": caps,
        "counters": counters,
        "budget_pct": int(raw.get("budget_pct") or 0),
        "overflow": raw.get("overflow"),
        "updated_at": raw.get("updated_at"),
    }


def _action_title(plan_md: str, action_index: int) -> str:
    try:
        action = find_dry_run_action(plan_md, action_index)
        if action is not None:
            label = getattr(action, "summary", None) or getattr(action, "what", None)
            return str(label or f"Action {action_index}").strip()
    except (ValueError, FileNotFoundError, LookupError, AttributeError):
        pass
    lines = plan_md.splitlines()
    head = f"{action_index}."
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(head):
            return stripped[len(head) :].strip() or f"Action {action_index}"
    return f"Action {action_index}"


def build_goal_chain(run: dict[str, Any], *, plan_md: str | None = None) -> list[dict[str, Any]]:
    """Ancestry path to current focus — not the full plan list."""
    chain: list[dict[str, Any]] = []
    verified = run.get("verified_loop")
    if isinstance(verified, dict):
        loop_goal = verified.get("loop_goal")
        if isinstance(loop_goal, dict) and str(loop_goal.get("text") or "").strip():
            chain.append({"kind": "verified_loop.loop_goal", "ref": "run.json"})
        elif str(verified.get("status") or "").strip():
            chain.append({"kind": "verified_loop", "ref": "run.json"})
    session_goal = run.get("session_goal")
    if isinstance(session_goal, dict) and str(session_goal.get("text") or "").strip():
        chain.append({"kind": "session_goal", "ref": "run.json"})

    from agent_lab.mission.loop import get_mission_loop

    ml = get_mission_loop(run)
    idx = ml.get("current_action_index")
    if idx is None:
        pending = ml.get("pending_action_indices") or []
        if pending:
            idx = pending[0]
    checkout = get_mission_board(run).get("checkout")
    if isinstance(checkout, dict) and checkout.get("action_index") is not None:
        idx = checkout.get("action_index")

    if idx is not None and plan_md:
        title = _action_title(plan_md, int(idx))
        chain.append(
            {
                "kind": "plan_action",
                "index": int(idx),
                "title": title,
            }
        )
    elif plan_md and ml.get("enabled"):
        actions = parse_plan_actions(plan_md)
        if len(actions) == 1:
            first = actions[0]
            label = str(first.summary or first.what or "Action 1").strip()
            chain.append(
                {
                    "kind": "plan_action",
                    "index": 1,
                    "title": label,
                }
            )
    return chain


def sync_mission_board(
    run: dict[str, Any],
    *,
    plan_md: str | None = None,
) -> dict[str, Any]:
    board = get_mission_board(run)
    board["goal_chain"] = build_goal_chain(run, plan_md=plan_md)
    run["mission_board"] = board
    return board


def patch_mission_board(
    folder: Path,
    updater: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]],
) -> dict[str, Any]:
    path = folder

    def _apply(run: dict[str, Any]) -> dict[str, Any]:
        board = get_mission_board(run)
        updated = updater(board, run)
        run["mission_board"] = updated if isinstance(updated, dict) else board
        return run

    patch_run_meta(path, _apply)
    return get_mission_board(read_run_meta(path))


def checkout_lane(
    folder: Path,
    lane: LaneId,
    *,
    action_index: int | None = None,
    execution_id: str | None = None,
) -> dict[str, Any]:
    path = folder

    def _checkout(board: dict[str, Any], _run: dict[str, Any]) -> dict[str, Any]:
        board["checkout"] = {
            "lane": lane,
            "action_index": action_index,
            "execution_id": execution_id,
            "checked_out_at": _now_iso(),
        }
        return board

    return patch_mission_board(path, _checkout)


def clear_checkout(folder: Path) -> dict[str, Any]:
    path = folder

    def _clear(board: dict[str, Any], _run: dict[str, Any]) -> dict[str, Any]:
        board["checkout"] = None
        return board

    return patch_mission_board(path, _clear)


def _compute_budget_pct(counters: dict[str, Any], caps: dict[str, Any]) -> int:
    ratios: list[float] = []
    agent_used = int(counters.get("agent_calls_per_human_turn") or 0)
    agent_cap = int(caps.get("agent_calls_per_human_turn") or 9)
    if agent_cap > 0:
        ratios.append(agent_used / agent_cap)
    mission_used = int(counters.get("mission_iterations") or 0)
    mission_cap = int(caps.get("mission_iterations") or 20)
    if mission_cap > 0:
        ratios.append(mission_used / mission_cap)
    tick_used = int(counters.get("autorun_ticks_this_hour") or 0)
    tick_cap = int(caps.get("autorun_ticks_per_hour") or 60)
    if tick_cap > 0:
        ratios.append(tick_used / tick_cap)
    if not ratios:
        return 0
    return min(100, int(max(ratios) * 100))


def refresh_turn_budget(run: dict[str, Any]) -> dict[str, Any]:
    tb = get_turn_budget(run)
    tb["budget_pct"] = _compute_budget_pct(tb["counters"], tb["caps"])
    tb["updated_at"] = _now_iso()
    run["turn_budget"] = tb
    return tb


def begin_human_turn(folder: Path, *, human_turn: int) -> dict[str, Any]:
    path = folder

    def _begin(run: dict[str, Any]) -> dict[str, Any]:
        tb = get_turn_budget(run)
        counters = dict(tb["counters"])
        counters["agent_calls_per_human_turn"] = 0
        counters["codex_shell_per_turn"] = 0
        counters["human_turn"] = human_turn
        tb["counters"] = counters
        tb["overflow"] = None
        run["turn_budget"] = refresh_turn_budget({**run, "turn_budget": tb})
        plan_md = None
        plan_path = path / "plan.md"
        if plan_path.is_file():
            try:
                plan_md = plan_path.read_text(encoding="utf-8")
            except OSError:
                plan_md = None
        sync_mission_board(run, plan_md=plan_md)
        return run

    patch_run_meta(path, _begin)
    return get_turn_budget(read_run_meta(path))


def _check_overflow(run: dict[str, Any]) -> tuple[str | None, str | None]:
    tb = get_turn_budget(run)
    counters = tb["counters"]
    caps = tb["caps"]
    agent_used = int(counters.get("agent_calls_per_human_turn") or 0)
    agent_cap = int(caps.get("agent_calls_per_human_turn") or 9)
    if agent_cap > 0 and agent_used > agent_cap:
        return (
            "agent_calls_per_human_turn",
            f"agent calls per human turn ({agent_used}/{agent_cap})",
        )
    tick_used = int(counters.get("autorun_ticks_this_hour") or 0)
    tick_cap = int(caps.get("autorun_ticks_per_hour") or 60)
    if tick_cap > 0 and tick_used > tick_cap:
        return (
            "autorun_ticks_per_hour",
            f"autorun ticks per hour ({tick_used}/{tick_cap})",
        )
    return None, None


def record_agent_call(
    folder: Path,
    *,
    human_turn: int,
    agent: str,
    run_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    path = folder

    def _record(run: dict[str, Any]) -> dict[str, Any]:
        tb = get_turn_budget(run)
        counters = dict(tb["counters"])
        if int(counters.get("human_turn") or 0) != human_turn:
            counters["human_turn"] = human_turn
            counters["agent_calls_per_human_turn"] = 0
        counters["agent_calls_per_human_turn"] = int(counters.get("agent_calls_per_human_turn") or 0) + 1
        tb["counters"] = counters
        run["turn_budget"] = refresh_turn_budget({**run, "turn_budget": tb})
        key, msg = _check_overflow(run)
        if key:
            run = _apply_overflow(run, key=key, message=msg or key)
        return run

    updated = patch_run_meta(path, _record)
    if run_meta is not None:
        run_meta["turn_budget"] = updated.get("turn_budget")
        run_meta["mission_board"] = updated.get("mission_board")
    return get_turn_budget(updated)


def record_autorun_tick(folder: Path) -> dict[str, Any]:
    path = folder
    bucket = _hour_bucket()

    def _tick(run: dict[str, Any]) -> dict[str, Any]:
        tb = get_turn_budget(run)
        counters = dict(tb["counters"])
        if counters.get("autorun_tick_hour") != bucket:
            counters["autorun_tick_hour"] = bucket
            counters["autorun_ticks_this_hour"] = 0
        counters["autorun_ticks_this_hour"] = int(counters.get("autorun_ticks_this_hour") or 0) + 1
        tb["counters"] = counters
        run["turn_budget"] = refresh_turn_budget({**run, "turn_budget": tb})
        key, msg = _check_overflow(run)
        if key == "autorun_ticks_per_hour" and msg:
            run = _apply_overflow(run, key=key, message=msg)
        return run

    updated = patch_run_meta(path, _tick)
    return get_turn_budget(updated)


def sync_turn_budget_from_mission(folder: Path) -> dict[str, Any]:
    """Mirror mission_loop.iteration into turn_budget counters."""
    from agent_lab.mission.loop import get_mission_loop

    path = folder

    def _sync(run: dict[str, Any]) -> dict[str, Any]:
        ml = get_mission_loop(run)
        tb = get_turn_budget(run)
        counters = dict(tb["counters"])
        counters["mission_iterations"] = int(ml.get("iteration") or 0)
        tb["counters"] = counters
        run["turn_budget"] = refresh_turn_budget({**run, "turn_budget": tb})
        return run

    updated = patch_run_meta(path, _sync)
    return get_turn_budget(updated)


def _apply_overflow(
    run: dict[str, Any],
    *,
    key: str,
    message: str,
) -> dict[str, Any]:
    tb = get_turn_budget(run)
    tb["overflow"] = {"key": key, "message": message, "at": _now_iso()}
    run["turn_budget"] = tb
    from agent_lab.mission.loop import get_mission_loop

    ml = get_mission_loop(run)
    if ml.get("enabled") and key in {"autorun_ticks_per_hour", "mission_iterations"}:
        return run
    from agent_lab.human_inbox import append_inbox_item, new_inbox_item

    item = new_inbox_item(
        kind="question",
        source="turn_budget",
        prompt=(f"Turn budget exceeded ({message}). Continue with a new human message or resolve in Inspector."),
        summary=f"turn_budget: {key}",
        options=[
            {"id": "continue", "label": "Acknowledge"},
            {"id": "pause", "label": "Pause mission"},
        ],
    )
    return append_inbox_item(run, item)


def handle_turn_budget_overflow(folder: Path, *, key: str, message: str) -> None:
    path = folder

    def _overflow(run: dict[str, Any]) -> dict[str, Any]:
        return _apply_overflow(run, key=key, message=message)

    patch_run_meta(path, _overflow)


def public_mission_board_payload(run: dict[str, Any]) -> dict[str, Any]:
    board = get_mission_board(run)
    checkout = board.get("checkout")
    return {
        "goal_chain": list(board.get("goal_chain") or []),
        "checkout": checkout,
        "lane_roles": dict(board.get("lane_roles") or default_lane_roles()),
        "checked_out": bool(checkout),
        "checkout_lane": checkout.get("lane") if isinstance(checkout, dict) else None,
    }


def public_turn_budget_payload(run: dict[str, Any]) -> dict[str, Any]:
    tb = get_turn_budget(run)
    return {
        "caps": dict(tb.get("caps") or {}),
        "counters": dict(tb.get("counters") or {}),
        "budget_pct": int(tb.get("budget_pct") or 0),
        "overflow": tb.get("overflow"),
        "updated_at": tb.get("updated_at"),
    }
