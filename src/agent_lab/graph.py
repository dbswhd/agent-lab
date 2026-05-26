from typing import TypedDict

from langgraph.graph import END, StateGraph

from agent_lab import roles
from agent_lab.invoke import invoke_role

MAX_LLM_CALLS = 3  # planner + critic + scribe (hard cap for cost education)


class GraphState(TypedDict):
    topic: str
    planner_output: str
    critic_output: str
    plan_md: str


def planner_node(state: GraphState) -> dict:
    user = f"Topic:\n{state['topic']}"
    return {"planner_output": invoke_role(roles.PLANNER, user)}


def critic_node(state: GraphState) -> dict:
    user = (
        f"Topic:\n{state['topic']}\n\n"
        f"Planner output:\n{state['planner_output']}"
    )
    return {"critic_output": invoke_role(roles.CRITIC, user)}


def scribe_node(state: GraphState) -> dict:
    user = (
        f"Topic:\n{state['topic']}\n\n"
        f"Planner output:\n{state['planner_output']}\n\n"
        f"Critic output:\n{state['critic_output']}"
    )
    return {"plan_md": invoke_role(roles.SCRIBE, user)}


def build_graph():
    g = StateGraph(GraphState)
    g.add_node("planner", planner_node)
    g.add_node("critic", critic_node)
    g.add_node("scribe", scribe_node)
    g.set_entry_point("planner")
    g.add_edge("planner", "critic")
    g.add_edge("critic", "scribe")
    g.add_edge("scribe", END)
    return g.compile()


def run_topic(topic: str) -> GraphState:
    graph = build_graph()
    initial: GraphState = {
        "topic": topic,
        "planner_output": "",
        "critic_output": "",
        "plan_md": "",
    }
    return graph.invoke(initial)
