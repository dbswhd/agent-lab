"""CLARIFY unification (Opt-B) — AC1..AC15.

C (clarity engine) backs A (server clarifier) behind AGENT_LAB_CLARIFIER_ENGINE while B
(plan_workflow) gates on clarity and delivers questions through the Human Inbox. OFF-parity
for each flag independently is the primary invariant.
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


def test_ac15_flag_registered_default_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGENT_LAB_CLARIFIER_ENGINE", raising=False)
    from agent_lab.clarifier_engine import engine_enabled
    from agent_lab.runtime_flags import FLAG_REGISTRY, _resolve_row

    row = next((f for f in FLAG_REGISTRY if f.name == "AGENT_LAB_CLARIFIER_ENGINE"), None)
    assert row is not None, "AGENT_LAB_CLARIFIER_ENGINE must be in the flag registry"
    assert row.default in ("", "0", "off", "false")
    # /api/health/flags is driven by _resolve_row → effective must read "off" by default.
    assert _resolve_row(row)["effective"] == "off"
    assert engine_enabled() is False


def test_engine_enabled_truthy_set(monkeypatch: pytest.MonkeyPatch) -> None:
    from agent_lab.clarifier_engine import engine_enabled

    for value in ("1", "true", "on", "yes"):
        monkeypatch.setenv("AGENT_LAB_CLARIFIER_ENGINE", value)
        assert engine_enabled() is True
    monkeypatch.setenv("AGENT_LAB_CLARIFIER_ENGINE", "0")
    assert engine_enabled() is False


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
    monkeypatch.setenv("AGENT_LAB_CLARIFIER_ENGINE", "1")
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


def test_ac1_engine_off_uses_static_templates(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    monkeypatch.setenv("AGENT_LAB_CLARIFIER", "1")
    monkeypatch.delenv("AGENT_LAB_CLARIFIER_ENGINE", raising=False)
    from agent_lab.session_clarifier import build_clarifier_interview

    interview = build_clarifier_interview("hi", is_new_session=True, human_message_count=1)
    assert interview is not None
    assert "source" not in interview, "engine-off static interviews carry no source marker"


def test_ac9_clarifier_off_engine_on_no_static_interview(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    monkeypatch.delenv("AGENT_LAB_CLARIFIER", raising=False)
    monkeypatch.setenv("AGENT_LAB_CLARIFIER_ENGINE", "1")
    from agent_lab.session_clarifier import build_clarifier_interview

    # A's surface still requires AGENT_LAB_CLARIFIER; engine flag alone does not strand it.
    assert build_clarifier_interview("make it better", is_new_session=True, human_message_count=1) is None


# ---------------------------------------------------------------- AC4 / AC12 persistence


def test_ac12_persist_returns_state_and_blocks_cross_source(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AGENT_LAB_CLARIFIER_ENGINE", "1")
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
    monkeypatch.setenv("AGENT_LAB_CLARIFIER_ENGINE", "1")
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


def test_ac1_persist_engine_off_legacy_overwrite(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("AGENT_LAB_CLARIFIER_ENGINE", raising=False)
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
    assert r["persisted"] is True and r["reason"] == "engine_off"
    # Legacy unconditional overwrite preserved when engine off (OFF-parity).
    assert get_clarifier_interview(read_run_meta(folder))["source"] == "server"


def test_ac14_off_parity_runjson_shape_byte_stable(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("AGENT_LAB_CLARIFIER_ENGINE", raising=False)
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
    # No engine-only keys injected into run.json when the engine is off.
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
    monkeypatch.setenv("AGENT_LAB_CLARIFIER_ENGINE", "1")
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
    monkeypatch.setenv("AGENT_LAB_CLARIFIER_ENGINE", "1")
    monkeypatch.delenv("AGENT_LAB_PIPELINE", raising=False)
    folder = _sess(tmp_path)
    _init_plan_workflow(folder)
    _seed_goal(folder, "fix src/agent_lab/run_meta.py null check")  # anchored => met

    tick = _tick(folder)
    assert tick.get("advance") == "DRAFT"


def test_ac8_gate_never_starts_execution(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    monkeypatch.setenv("AGENT_LAB_CLARIFIER_ENGINE", "1")
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


def test_ac1_gate_off_parity_engine_off_advances(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    monkeypatch.delenv("AGENT_LAB_CLARIFIER_ENGINE", raising=False)  # engine OFF
    monkeypatch.delenv("AGENT_LAB_PIPELINE", raising=False)
    from agent_lab.human_inbox import has_pending_question

    folder = _sess(tmp_path)
    _init_plan_workflow(folder)
    _seed_goal(folder, "make the whole thing better somehow")  # vague

    tick = _tick(folder)
    # Legacy round-counter behavior: advances to DRAFT despite vagueness; no inbox question.
    assert tick.get("advance") == "DRAFT"
    assert has_pending_question(read_run_meta(folder)) is False


def test_ac9_gate_reachable_with_clarifier_flag_off(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """CLARIFIER=0 + ENGINE=1 + PIPELINE=1: B still delivers via Human Inbox (A flag-independent)."""
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    monkeypatch.delenv("AGENT_LAB_CLARIFIER", raising=False)  # A surface flag OFF
    monkeypatch.setenv("AGENT_LAB_CLARIFIER_ENGINE", "1")
    monkeypatch.delenv("AGENT_LAB_PIPELINE", raising=False)
    from agent_lab.human_inbox import has_pending_question

    folder = _sess(tmp_path)
    _init_plan_workflow(folder)
    _seed_goal(folder, "make the whole thing better somehow")

    tick = _tick(folder)
    assert tick.get("clarity_pending") is True
    assert has_pending_question(read_run_meta(folder)) is True
