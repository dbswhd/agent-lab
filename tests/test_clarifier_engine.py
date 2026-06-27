"""CLARIFY engine always-on — AC1..AC15.

Clarity engine is always active: vague topics hold CLARIFY; anchored topics pass immediately
via regex short-circuit (no LLM call). Identity-aware persistence is always in effect.
AGENT_LAB_CLARIFIER_ENGINE is removed; AGENT_LAB_CLARIFIER still gates the A-surface.
"""

from __future__ import annotations

import ast
import typing
from pathlib import Path

import pytest

from agent_lab.run_meta import patch_run_meta, read_run_meta


def _sess(tmp_path: Path) -> Path:
    folder = tmp_path / "sess"
    folder.mkdir()
    (folder / "run.json").write_text("{}", encoding="utf-8")
    return folder


def _seed_goal(folder: Path, text: str) -> None:
    def _patch(run: dict) -> dict:
        loop = run.get("verified_loop")
        loop = loop if isinstance(loop, dict) else {}
        loop["loop_goal"] = {"text": text}
        run["verified_loop"] = loop
        return run

    patch_run_meta(folder, _patch)


# ---------------------------------------------------------------- AC15 / registry


def test_ac15_clarifier_engine_flag_removed_from_registry() -> None:
    from agent_lab.runtime_flags import FLAG_REGISTRY

    names = {f.name for f in FLAG_REGISTRY}
    assert "AGENT_LAB_CLARIFIER_ENGINE" not in names, "flag must be removed — engine is always on"


# ---------------------------------------------------------------- adapter purity / cycle


def test_adapter_is_pure_no_storage_no_toplevel_ac_imports() -> None:
    import agent_lab.clarifier_engine as ce

    src = Path(ce.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)

    # No storage writes: the adapter must never reference run_meta persistence helpers in code.
    identifiers: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            identifiers.add(node.id)
        elif isinstance(node, ast.Attribute):
            identifiers.add(node.attr)
    assert "patch_run_meta" not in identifiers, "adapter must perform no storage writes"

    # No A/C imports at module top level (cycle safety) — only lazy/in-function imports allowed.
    toplevel = [n for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom))]
    modules: list[str] = []
    for node in toplevel:
        if isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
        elif isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
    assert not any(m.endswith("run_meta") for m in modules), "adapter must not import run_meta"
    assert not any(m.endswith("session_clarifier") or m.endswith("clarity") for m in modules), (
        "adapter must not import A/C at module top level (cycle safety)"
    )


def test_import_cycle_safe() -> None:
    import importlib

    for mod in ("agent_lab.clarity", "agent_lab.clarifier_engine", "agent_lab.session_clarifier"):
        importlib.import_module(mod)


# ---------------------------------------------------------------- AC5 / AC6 / AC13 engine


def test_ac5_engine_anchor_skip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    from agent_lab.clarifier_engine import build_engine_interview, engine_questions

    assert build_engine_interview("fix src/agent_lab/run_meta.py", human_message_count=1) is None
    _result, questions = engine_questions("fix src/agent_lab/run_meta.py")
    assert questions == []


def test_ac6_engine_mock_deterministic(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    from agent_lab.clarifier_engine import build_engine_interview, engine_questions

    _r1, q1 = engine_questions("make the whole thing better somehow")
    _r2, q2 = engine_questions("make the whole thing better somehow")
    assert q1 == q2 and q1, "vague text must deterministically yield questions"
    interview = build_engine_interview("make the whole thing better somehow", human_message_count=1)
    assert interview is not None
    assert interview["source"] == "clarity_engine"
    assert interview["version"] == 2 and interview["status"] == "pending"
    assert interview["questions"]


def test_ac13_one_pass_single_panel(monkeypatch: pytest.MonkeyPatch) -> None:
    """engine_questions must score the panel exactly once (no double scoring)."""
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "0")
    monkeypatch.delenv("AGENT_LAB_CLARITY_TOPOLOGY", raising=False)
    import agent_lab.agents.registry as reg

    calls: list[str] = []

    def fake_call_agent(agent, system, user, **_kwargs):  # noqa: ANN001, ANN202
        calls.append(str(agent))
        return "goal=0.6 constraints=0.6 criteria=0.6 context=0.6"

    monkeypatch.setattr(reg, "available_agents", lambda: ["codex", "claude", "cursor"])
    monkeypatch.setattr(reg, "call_agent", fake_call_agent)

    from agent_lab.clarifier_engine import engine_questions

    _result, questions = engine_questions("make the whole thing better somehow please")
    assert questions, "vague task must surface questions"
    # One pass = at most one call per panelist (<=3). A double-score path would be ~6.
    assert len(calls) <= 3


# ---------------------------------------------------------------- AC11 category contract


def test_ac11_category_literal_includes_criteria_context() -> None:
    from agent_lab.session_clarifier import ClarifierCategory

    args = set(typing.get_args(ClarifierCategory))
    assert {"goal", "scope", "verify", "constraints", "priority", "criteria", "context"} <= args


# ---------------------------------------------------------------- AC2 / AC1 build surface


def test_ac2_engine_backed_build_surface(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    monkeypatch.setenv("AGENT_LAB_CLARIFIER", "1")
    from agent_lab.session_clarifier import build_clarifier_interview

    interview = build_clarifier_interview(
        "make the whole thing better somehow", is_new_session=True, human_message_count=1
    )
    assert interview is not None
    assert interview["source"] == "clarity_engine"
    assert interview["version"] == 2 and interview["status"] == "pending"
    categories = {q["category"] for q in interview["questions"]}
    assert categories <= {"goal", "constraints", "criteria", "context"}
    assert categories, "engine-backed surface must carry clarity-engine categories"


def test_ac1_vague_topic_uses_engine_interview(monkeypatch: pytest.MonkeyPatch) -> None:
    """Engine always on: vague short topic → engine interview with source marker."""
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    monkeypatch.setenv("AGENT_LAB_CLARIFIER", "1")
    from agent_lab.session_clarifier import build_clarifier_interview

    interview = build_clarifier_interview("hi", is_new_session=True, human_message_count=1)
    assert interview is not None
    assert interview["source"] == "clarity_engine", "engine always on → source marker present"


def test_ac9_clarifier_off_engine_on_no_static_interview(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    monkeypatch.delenv("AGENT_LAB_CLARIFIER", raising=False)
    from agent_lab.session_clarifier import build_clarifier_interview

    # A's surface still requires AGENT_LAB_CLARIFIER; engine alone does not enable it.
    assert build_clarifier_interview("make it better", is_new_session=True, human_message_count=1) is None


# ---------------------------------------------------------------- AC4 / AC12 persistence


def test_ac12_persist_returns_state_and_blocks_cross_source(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    folder = _sess(tmp_path)
    from agent_lab.session_clarifier import get_clarifier_interview, persist_clarifier_interview

    panel = {
        "version": 2,
        "status": "pending",
        "source": "clarify_panel",
        "questions": [{"id": "q1", "category": "goal", "prompt": "Q?"}],
        "answers": {},
    }
    r1 = persist_clarifier_interview(folder, panel)
    assert r1["persisted"] is True
    assert r1["interview"]["source"] == "clarify_panel"

    server = {
        "version": 2,
        "status": "pending",
        "source": "server",
        "questions": [{"id": "s1", "category": "goal", "prompt": "S?"}],
        "answers": {},
    }
    r2 = persist_clarifier_interview(folder, server)
    assert r2["persisted"] is False
    assert r2["reason"] == "cross_source_pending"
    assert r2["interview"]["source"] == "clarify_panel"  # preserved
    assert get_clarifier_interview(read_run_meta(folder))["source"] == "clarify_panel"

    panel2 = {**panel, "questions": [{"id": "q1", "category": "goal", "prompt": "Q-refined?"}]}
    r3 = persist_clarifier_interview(folder, panel2)
    assert r3["persisted"] is True and r3["reason"] == "same_source_update"

    r4 = persist_clarifier_interview(folder, server, replace=True)
    assert r4["persisted"] is True and r4["reason"] == "explicit_replace"
    assert get_clarifier_interview(read_run_meta(folder))["source"] == "server"


def test_ac4_completion_only_via_record_then_next_pending(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    folder = _sess(tmp_path)
    from agent_lab.session_clarifier import persist_clarifier_interview, record_clarifier_answers

    interview = {
        "version": 2,
        "status": "pending",
        "source": "clarity_engine",
        "questions": [{"id": "q1", "category": "goal", "prompt": "Q?"}],
        "answers": {},
    }
    persist_clarifier_interview(folder, interview)
    public = record_clarifier_answers(folder, answers={"q1": "the answer"})
    assert public is not None and public["status"] == "complete"

    nxt = {
        "version": 2,
        "status": "pending",
        "source": "server",
        "questions": [{"id": "s1", "category": "goal", "prompt": "S?"}],
        "answers": {},
    }
    r = persist_clarifier_interview(folder, nxt)
    assert r["persisted"] is True and r["reason"] == "prior_complete"


def test_ac1_persist_cross_source_pending_always_blocked(tmp_path: Path) -> None:
    """Identity-aware persistence always on: cross-source pending write is blocked."""
    folder = _sess(tmp_path)
    from agent_lab.session_clarifier import get_clarifier_interview, persist_clarifier_interview

    a = {
        "version": 2,
        "status": "pending",
        "source": "clarify_panel",
        "questions": [{"id": "q1", "category": "goal", "prompt": "A?"}],
        "answers": {},
    }
    persist_clarifier_interview(folder, a)
    b = {
        "version": 2,
        "status": "pending",
        "source": "server",
        "questions": [{"id": "q2", "category": "goal", "prompt": "B?"}],
        "answers": {},
    }
    r = persist_clarifier_interview(folder, b)
    assert r["persisted"] is False and r["reason"] == "cross_source_pending"
    # Existing panel interview is preserved.
    assert get_clarifier_interview(read_run_meta(folder))["source"] == "clarify_panel"


def test_ac14_persist_stores_candidate_verbatim(tmp_path: Path) -> None:
    """persist_clarifier_interview does not inject extra keys into run.json."""
    folder = _sess(tmp_path)
    from agent_lab.session_clarifier import get_clarifier_interview, persist_clarifier_interview

    candidate = {
        "version": 2,
        "status": "pending",
        "questions": [{"id": "q1", "category": "goal", "prompt": "Q?"}],
        "answers": {},
    }
    persist_clarifier_interview(folder, candidate)
    stored = get_clarifier_interview(read_run_meta(folder))
    assert stored == candidate


# ---------------------------------------------------------------- AC3 / AC8 / AC10 gate


def _init_plan_workflow(folder: Path) -> None:
    from agent_lab.plan_workflow import init_plan_workflow_on_plan_send

    init_plan_workflow_on_plan_send(folder)


def _tick(folder: Path) -> dict:
    from agent_lab.plan_workflow import tick_plan_workflow_after_turn

    return tick_plan_workflow_after_turn(
        folder,
        synthesize=True,
        cancelled=False,
        plan_md="",
        plan_before="",
        has_pending_inbox_question=False,
    )


def test_ac10_gate_holds_clarify_with_visible_inbox_question(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    monkeypatch.setenv("AGENT_LAB_ORCHESTRATOR_INBOX_HARVEST", "1")
    monkeypatch.delenv("AGENT_LAB_PIPELINE", raising=False)  # default ON
    from agent_lab.human_inbox import has_pending_question
    from agent_lab.plan_workflow import get_plan_workflow

    folder = _sess(tmp_path)
    _init_plan_workflow(folder)
    _seed_goal(folder, "make the whole thing better somehow")  # vague => clarity unmet

    tick = _tick(folder)
    assert tick["phase"] == "CLARIFY"
    assert tick.get("clarity_pending") is True
    # AC10: a human-visible pending Human Inbox question MUST exist when holding.
    assert has_pending_question(read_run_meta(folder)) is True
    assert get_plan_workflow(read_run_meta(folder))["phase"] == "CLARIFY"


def test_ac3_gate_advances_when_clarity_met(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    monkeypatch.delenv("AGENT_LAB_PIPELINE", raising=False)
    folder = _sess(tmp_path)
    _init_plan_workflow(folder)
    _seed_goal(folder, "fix src/agent_lab/run_meta.py null check")  # anchored => met

    tick = _tick(folder)
    assert tick.get("advance") == "DRAFT"


def test_ac8_gate_never_starts_execution(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    monkeypatch.setenv("AGENT_LAB_ORCHESTRATOR_INBOX_HARVEST", "1")
    monkeypatch.delenv("AGENT_LAB_PIPELINE", raising=False)
    from agent_lab.plan_workflow import get_plan_workflow

    folder = _sess(tmp_path)
    _init_plan_workflow(folder)
    _seed_goal(folder, "make the whole thing better somehow")

    _tick(folder)
    run = read_run_meta(folder)
    # Clarity gating never bypasses approval: phase stays CLARIFY, loop never "running".
    assert get_plan_workflow(run)["phase"] == "CLARIFY"
    assert (run.get("verified_loop") or {}).get("status") != "running"


def test_ac1_gate_anchored_topic_advances_to_draft(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Engine always on: anchored topic (regex short-circuit) → advances to DRAFT immediately."""
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    monkeypatch.delenv("AGENT_LAB_PIPELINE", raising=False)
    from agent_lab.human_inbox import has_pending_question

    folder = _sess(tmp_path)
    _init_plan_workflow(folder)
    _seed_goal(folder, "fix src/agent_lab/run_meta.py null check")  # anchored → clarity met

    tick = _tick(folder)
    assert tick.get("advance") == "DRAFT"
    assert has_pending_question(read_run_meta(folder)) is False


def test_ac9_gate_reachable_with_clarifier_flag_off(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """CLARIFIER=0 + PIPELINE=1: B still delivers via Human Inbox (A flag-independent)."""
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    monkeypatch.delenv("AGENT_LAB_CLARIFIER", raising=False)  # A surface flag OFF
    monkeypatch.setenv("AGENT_LAB_ORCHESTRATOR_INBOX_HARVEST", "1")
    monkeypatch.delenv("AGENT_LAB_PIPELINE", raising=False)
    from agent_lab.human_inbox import has_pending_question

    folder = _sess(tmp_path)
    _init_plan_workflow(folder)
    _seed_goal(folder, "make the whole thing better somehow")

    tick = _tick(folder)
    assert tick.get("clarity_pending") is True
    assert has_pending_question(read_run_meta(folder)) is True


def test_ac10b_mcp_first_engine_on_holds_clarify(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """AC10b: MCP-first (harvest off default) → CLARIFY holds without inbox item."""
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    monkeypatch.delenv("AGENT_LAB_ORCHESTRATOR_INBOX_HARVEST", raising=False)  # default 0 = MCP-first
    monkeypatch.delenv("AGENT_LAB_PIPELINE", raising=False)
    from agent_lab.human_inbox import has_pending_question
    from agent_lab.plan_workflow import get_plan_workflow

    folder = _sess(tmp_path)
    _init_plan_workflow(folder)
    _seed_goal(folder, "make the whole thing better somehow")  # vague → clarity unmet

    tick = _tick(folder)
    assert tick["phase"] == "CLARIFY"
    assert tick.get("clarity_pending") is True
    assert tick.get("clarity_notice") == "clarity_mcp_first_hold"
    # MCP-first: no inbox item, but CLARIFY holds (agents surface via ask_human/chat).
    assert has_pending_question(read_run_meta(folder)) is False
    assert get_plan_workflow(read_run_meta(folder))["phase"] == "CLARIFY"
