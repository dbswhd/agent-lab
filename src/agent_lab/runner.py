"""Run graph with per-node progress callbacks (for API / UI)."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

from agent_lab import roles
from agent_lab.invoke import invoke_role, model_name, provider, reset_provider_override, set_provider_override
from agent_lab.session import save_session

if TYPE_CHECKING:
    from agent_lab.graph import GraphState

StepCallback = Callable[[str, str, dict[str, Any] | None], None]
# (node, status, extra) — status: running | done | error


@contextmanager
def provider_override(name: str | None):
    if not name:
        yield
        return
    token = set_provider_override(name.strip().lower())
    try:
        yield
    finally:
        reset_provider_override(token)


def run_topic_with_progress(
    topic: str,
    on_step: StepCallback | None = None,
    *,
    backend: str | None = None,
    sessions_base=None,
) -> tuple[GraphState, Any]:
    def emit(node: str, status: str, extra: dict[str, Any] | None = None) -> None:
        if on_step:
            on_step(node, status, extra)

    state: GraphState = {
        "topic": topic,
        "planner_output": "",
        "critic_output": "",
        "plan_md": "",
    }

    with provider_override(backend):
        emit("init", "running", {"backend": provider(), "model": model_name()})
        emit("init", "done")

        emit("planner", "running")
        state["planner_output"] = invoke_role(roles.PLANNER, f"Topic:\n{topic}")
        emit("planner", "done", {"chars": len(state["planner_output"])})

        emit("critic", "running")
        user = f"Topic:\n{topic}\n\nPlanner output:\n{state['planner_output']}"
        state["critic_output"] = invoke_role(roles.CRITIC, user)
        emit("critic", "done", {"chars": len(state["critic_output"])})

        emit("scribe", "running")
        user = (
            f"Topic:\n{topic}\n\nPlanner output:\n{state['planner_output']}\n\nCritic output:\n{state['critic_output']}"
        )
        state["plan_md"] = invoke_role(roles.SCRIBE, user)
        emit("scribe", "done", {"chars": len(state["plan_md"])})

        emit("save", "running")
        folder = save_session(state, base=sessions_base)
        emit("save", "done", {"path": str(folder)})

    return state, folder
