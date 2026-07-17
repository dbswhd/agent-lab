"""CX8 (09-context-engineering.md §11) — the actual splice point in
context/bundle.py::build_context_bundle.

The critical invariant: AGENT_LAB_CONTEXT_RECIPE must NEVER change what
build_context_bundle returns, on or off, success or failure inside the
shadow pass. These tests drive build_context_bundle itself (not
shadow_compare_bundle directly -- see test_context_bundle_shadow.py for
that), toggling the flag via monkeypatch.
"""

from __future__ import annotations

from dataclasses import dataclass

from agent_lab.context.bundle import build_context_bundle


@dataclass
class _Msg:
    role: str
    agent: str | None
    content: str
    parallel_round: int | None = None


def _format_thread(topic: str, messages: list[_Msg]) -> str:
    lines = [f"Human topic:\n{topic}\n"]
    for m in messages:
        if m.role == "user":
            lines.append(f"Human:\n{m.content}\n")
        elif m.role == "agent" and m.agent:
            lines.append(f"{m.agent}:\n{m.content}\n")
    return "\n".join(lines)


def _messages() -> list[_Msg]:
    return [_Msg("user", None, "please fix the bug"), _Msg("agent", "codex", "on it", 1)]


def test_flag_off_by_default_produces_identical_bundle_to_before_this_change() -> None:
    """No env var set at all -- matches every pre-existing bundle.py test's
    environment. Asserts the same invariants test_context_bundle.py's own
    test_build_context_bundle_has_layers_and_meta does, as a belt-and-
    suspenders check that the splice didn't perturb the default path."""
    bundle = build_context_bundle("topic", _messages(), "cursor", format_thread=_format_thread)
    text = bundle.render()
    assert "[고정 constraints]" in text
    assert "[plan 미결]" in text
    assert "[최근 N턴]" in text
    assert bundle.meta.layer_chars["total"] == len(text)


def test_flag_on_produces_byte_identical_render_to_flag_off(monkeypatch) -> None:
    """The core CX8 safety invariant: enabling AGENT_LAB_CONTEXT_RECIPE must
    not change a single character of what build_context_bundle returns."""
    run_meta_off: dict = {}
    bundle_off = build_context_bundle(
        "topic", _messages(), "cursor", format_thread=_format_thread, run_meta=run_meta_off,
    )

    monkeypatch.setenv("AGENT_LAB_CONTEXT_RECIPE", "1")
    run_meta_on: dict = {}
    bundle_on = build_context_bundle(
        "topic", _messages(), "cursor", format_thread=_format_thread, run_meta=run_meta_on,
    )

    assert bundle_on.render() == bundle_off.render()
    assert bundle_on.meta.layer_chars == bundle_off.meta.layer_chars


def test_flag_on_produces_byte_identical_render_on_the_slim_path_too(monkeypatch) -> None:
    """DISCUSS/PLAN_GATE/PLAN_REJECT redirect to build_slim_consensus_bundle
    BEFORE build_context_bundle's own tail ever runs -- this is the second,
    separately-spliced shadow call site, and needs the same byte-identical
    guarantee."""
    def _discuss_run_meta() -> dict:
        return {"mission_loop": {"enabled": True, "phase": "DISCUSS"}}

    run_meta_off = _discuss_run_meta()
    bundle_off = build_context_bundle(
        "topic", _messages(), "cursor", format_thread=_format_thread, run_meta=run_meta_off,
    )

    monkeypatch.setenv("AGENT_LAB_CONTEXT_RECIPE", "1")
    run_meta_on = _discuss_run_meta()
    bundle_on = build_context_bundle(
        "topic", _messages(), "cursor", format_thread=_format_thread, run_meta=run_meta_on,
    )

    assert bundle_on.render() == bundle_off.render()
    assert bundle_on.meta.slim_context is True  # confirms this actually hit the slim path


def test_flag_on_stamps_a_shadow_result_into_run_meta(monkeypatch) -> None:
    monkeypatch.setenv("AGENT_LAB_CONTEXT_RECIPE", "1")
    run_meta: dict = {"mission_loop": {"enabled": True, "phase": "DISCUSS"}}
    build_context_bundle("topic", _messages(), "cursor", format_thread=_format_thread, run_meta=run_meta)
    assert "context_recipe_shadow" in run_meta
    shadow = run_meta["context_recipe_shadow"]
    assert "ok" in shadow


def test_flag_on_without_mission_loop_still_returns_the_bundle_unbroken(monkeypatch) -> None:
    """No mission_loop in run_meta at all -- activity_kind_for_mission_phase
    returns None, shadow_compare_bundle reports a skip, but
    build_context_bundle must still return normally."""
    monkeypatch.setenv("AGENT_LAB_CONTEXT_RECIPE", "1")
    run_meta: dict = {}
    bundle = build_context_bundle("topic", _messages(), "cursor", format_thread=_format_thread, run_meta=run_meta)
    assert bundle.render()
    assert run_meta["context_recipe_shadow"]["ok"] is False
    assert run_meta["context_recipe_shadow"].get("skipped") is True


def test_flag_on_with_no_run_meta_at_all_does_not_crash(monkeypatch) -> None:
    """run_meta=None (a valid call shape -- see build_context_bundle's own
    default) must not crash the shadow pass or the live call."""
    monkeypatch.setenv("AGENT_LAB_CONTEXT_RECIPE", "1")
    bundle = build_context_bundle("topic", _messages(), "cursor", format_thread=_format_thread, run_meta=None)
    assert bundle.render()


def test_flag_on_shadow_failure_never_propagates(monkeypatch) -> None:
    """Force shadow_compare_bundle to raise -- build_context_bundle must
    still return the legacy bundle untouched, per the try/except at the
    splice point."""
    monkeypatch.setenv("AGENT_LAB_CONTEXT_RECIPE", "1")

    def _boom(**kwargs):
        raise RuntimeError("simulated shadow failure")

    import agent_lab.context.bundle_shadow as bundle_shadow

    monkeypatch.setattr(bundle_shadow, "shadow_compare_bundle", _boom)
    run_meta: dict = {"mission_loop": {"enabled": True, "phase": "DISCUSS"}}
    bundle = build_context_bundle("topic", _messages(), "cursor", format_thread=_format_thread, run_meta=run_meta)
    assert bundle.render()
    # the try/except swallows the failure before stamping ever happens
    assert "context_recipe_shadow" not in run_meta
