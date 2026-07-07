"""C3 — risk-inverse profile pin unit tests (mock-only, no real I/O beyond tmp_path).

docs/N10-USER-LOOP-WISDOM-DRAFT.md §4-C3.
"""

from __future__ import annotations

import json

from agent_lab.autonomy_ladder import record_autonomy_transition, stored_autonomy_level
from agent_lab.human_inbox import inbox_items
from agent_lab.risk_pin import maybe_apply_risk_pin
from agent_lab.run.meta import patch_run_meta, read_run_meta


def _write_session(folder, *, category: str = "trading") -> None:
    folder.mkdir(parents=True, exist_ok=True)
    run = {
        "topic": "trading mission",
        "turns": [{"category": {"value": category}}],
    }
    (folder / "run.json").write_text(json.dumps(run), encoding="utf-8")


def test_noop_when_category_not_risky(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_LAB_RISK_PIN", "1")
    _write_session(tmp_path, category="standard")
    assert maybe_apply_risk_pin(tmp_path, 1) is None
    assert read_run_meta(tmp_path).get("risk_pin") is None


def test_noop_without_turns(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_LAB_RISK_PIN", "1")
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "run.json").write_text(json.dumps({"topic": "x"}), encoding="utf-8")
    assert maybe_apply_risk_pin(tmp_path, 1) is None


def test_flag_off_is_noop(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_LAB_RISK_PIN", "0")
    _write_session(tmp_path)
    record_autonomy_transition(tmp_path, to_level="L3", reason="test setup", trigger="human")
    assert maybe_apply_risk_pin(tmp_path, 1) is None
    assert read_run_meta(tmp_path).get("risk_pin") is None
    assert stored_autonomy_level(read_run_meta(tmp_path)) == "L3"


def test_pins_ceiling_down_from_l3_to_l1(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_LAB_RISK_PIN", "1")
    _write_session(tmp_path)
    record_autonomy_transition(tmp_path, to_level="L3", reason="test setup", trigger="human")

    marker = maybe_apply_risk_pin(tmp_path, 1)
    assert marker is not None
    assert marker["category"] == "trading"

    run = read_run_meta(tmp_path)
    assert stored_autonomy_level(run) == "L1"
    assert run.get("risk_pin", {}).get("category") == "trading"


def test_pins_creates_demotion_inbox_item(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_LAB_RISK_PIN", "1")
    _write_session(tmp_path)
    record_autonomy_transition(tmp_path, to_level="L2", reason="test setup", trigger="human")

    maybe_apply_risk_pin(tmp_path, 1)

    run = read_run_meta(tmp_path)
    pending = [i for i in inbox_items(run) if i.get("kind") == "autonomy" and i.get("status") == "pending"]
    assert len(pending) == 1
    assert pending[0]["harvest_key"] == "autonomy:demotion:L2:L1"
    assert any(opt["id"] == "restore:L2" for opt in pending[0]["options"])


def test_no_transition_when_already_at_or_below_l1(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_LAB_RISK_PIN", "1")
    _write_session(tmp_path)
    record_autonomy_transition(tmp_path, to_level="L0", reason="test setup", trigger="human")

    marker = maybe_apply_risk_pin(tmp_path, 1)
    assert marker is not None
    # ceiling already L0 <= L1 — pin marker recorded, but no new autonomy transition/inbox noise
    run = read_run_meta(tmp_path)
    assert stored_autonomy_level(run) == "L0"
    pending = [i for i in inbox_items(run) if i.get("kind") == "autonomy" and i.get("status") == "pending"]
    assert pending == []


def test_idempotent_does_not_repin_after_human_override(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_LAB_RISK_PIN", "1")
    _write_session(tmp_path)
    record_autonomy_transition(tmp_path, to_level="L3", reason="test setup", trigger="human")

    first = maybe_apply_risk_pin(tmp_path, 1)
    assert first is not None
    assert stored_autonomy_level(read_run_meta(tmp_path)) == "L1"

    # Human explicitly overrides the pin, raising the ceiling back to L3.
    record_autonomy_transition(tmp_path, to_level="L3", reason="human restore", trigger="human")

    # A later turn with the same risk category must NOT re-lower the ceiling.
    second = maybe_apply_risk_pin(tmp_path, 2)
    assert second is None
    assert stored_autonomy_level(read_run_meta(tmp_path)) == "L3"


def test_fails_open_on_missing_session(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_LAB_RISK_PIN", "1")
    folder = tmp_path / "does-not-exist"
    assert maybe_apply_risk_pin(folder, 1) is None


def test_marker_persists_pinned_at_and_ceiling(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_LAB_RISK_PIN", "1")
    _write_session(tmp_path)
    record_autonomy_transition(tmp_path, to_level="L2", reason="test setup", trigger="human")

    marker = maybe_apply_risk_pin(tmp_path, 1)
    assert marker["ceiling"] == "L1"
    assert marker["pinned_at"]


def test_escalates_to_new_category_after_prior_pin(tmp_path, monkeypatch):
    """A different risky category should re-pin even if one was already recorded."""
    monkeypatch.setenv("AGENT_LAB_RISK_PIN", "1")
    _write_session(tmp_path, category="trading")
    record_autonomy_transition(tmp_path, to_level="L3", reason="test setup", trigger="human")
    maybe_apply_risk_pin(tmp_path, 1)
    assert read_run_meta(tmp_path).get("risk_pin", {}).get("category") == "trading"

    # Human restores ceiling, then a hypothetical second risk category appears in a later turn.
    record_autonomy_transition(tmp_path, to_level="L3", reason="human restore", trigger="human")

    def _bump_category(run):
        run["turns"][-1]["category"] = {"value": "payment"}
        return run

    patch_run_meta(tmp_path, _bump_category)
    monkeypatch.setattr("agent_lab.risk_pin.RISK_CATEGORIES", frozenset({"trading", "payment"}))

    marker = maybe_apply_risk_pin(tmp_path, 2)
    assert marker is not None
    assert marker["category"] == "payment"
    assert stored_autonomy_level(read_run_meta(tmp_path)) == "L1"
