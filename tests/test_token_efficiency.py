"""세션 비용 라이브 가시화 + 적응형 efficiency 강등 테스트.

Mock-only: cost_ledger.session_budget_action, room_turn_flow budget emit /
adaptive flag / hard-cap, run.json roundtrip, and the hard-cap preflight helper.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

os.environ.setdefault("AGENT_LAB_MOCK_AGENTS", "1")

from agent_lab.cost_ledger import session_budget_action
from agent_lab.room_turn_flow import (
    _emit_budget_status,
    _session_hard_cap_enabled,
)


@pytest.fixture
def clean_budget_env(monkeypatch):
    for k in ("AGENT_LAB_SESSION_TOKEN_BUDGET", "AGENT_LAB_MISSION_BUDGET_USD", "AGENT_LAB_SESSION_HARD_CAP"):
        monkeypatch.delenv(k, raising=False)
    return monkeypatch


def _ledger(tokens_in=0, tokens_out=0, usd=0.0):
    return {"cost_ledger": {"cumulative": {"tokens_in": tokens_in, "tokens_out": tokens_out, "usd": usd}}}


class _Events:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    def __call__(self, kind, payload):
        self.events.append((kind, payload))

    def kinds(self):
        return [k for k, _ in self.events]


# --- session_budget_action -----------------------------------------------


def test_surface_without_budget(clean_budget_env):
    a = session_budget_action(_ledger(100, 50, 0.02))
    assert a["surface"] is True
    assert a["budget_set"] is False
    assert a["warn"] is False and a["over"] is False
    assert a["cumulative"] == {"tokens_in": 100, "tokens_out": 50, "tokens_total": 150, "usd": 0.02}


def test_token_budget_over(clean_budget_env):
    clean_budget_env.setenv("AGENT_LAB_SESSION_TOKEN_BUDGET", "120")
    a = session_budget_action(_ledger(100, 50, 0.0))
    assert a["budget_set"] is True and a["over"] is True and a["warn"] is True
    assert a["suggest_efficiency"] is True
    assert a["token_limit"] == 120


def test_token_budget_warn_not_over(clean_budget_env):
    clean_budget_env.setenv("AGENT_LAB_SESSION_TOKEN_BUDGET", "1000")  # warn at 80% = 800
    a = session_budget_action(_ledger(500, 350, 0.0))  # 850 total
    assert a["warn"] is True and a["over"] is False


def test_usd_budget_over(clean_budget_env):
    clean_budget_env.setenv("AGENT_LAB_MISSION_BUDGET_USD", "1.00")
    a = session_budget_action(_ledger(10, 10, 1.50))
    assert a["over"] is True and a["budget_set"] is True
    assert a["usd_limit"] == 1.00


def test_over_is_or_of_usd_and_token(clean_budget_env):
    # token cap crossed, usd cap not -> over via OR
    clean_budget_env.setenv("AGENT_LAB_SESSION_TOKEN_BUDGET", "50")
    clean_budget_env.setenv("AGENT_LAB_MISSION_BUDGET_USD", "100.0")
    a = session_budget_action(_ledger(40, 40, 0.01))  # 80 tokens > 50, usd 0.01 < 100
    assert a["over"] is True


def test_no_ledger_safe(clean_budget_env):
    a = session_budget_action({})
    assert a["surface"] is True and a["over"] is False
    assert a["cumulative"]["tokens_total"] == 0


# --- _emit_budget_status ---------------------------------------------------


def test_emit_always_surfaces_budget_status(clean_budget_env):
    ev = _Events()
    _emit_budget_status(_ledger(5, 5, 0.0), ev)
    assert ev.kinds() == ["budget_status"]


def test_emit_over_enables_adaptive_efficiency_once(clean_budget_env):
    clean_budget_env.setenv("AGENT_LAB_SESSION_TOKEN_BUDGET", "100")
    rm = _ledger(80, 40, 0.0)  # 120 > 100
    ev = _Events()
    _emit_budget_status(rm, ev)
    assert "budget_status" in ev.kinds() and "efficiency_auto_enabled" in ev.kinds()
    assert rm["adaptive_efficiency"] is True
    assert rm["budget_status"]["over"] is True  # persisted snapshot
    # second turn: no duplicate efficiency_auto_enabled
    ev2 = _Events()
    _emit_budget_status(rm, ev2)
    assert ev2.kinds() == ["budget_status"]


def test_emit_under_budget_no_flag(clean_budget_env):
    clean_budget_env.setenv("AGENT_LAB_SESSION_TOKEN_BUDGET", "10000")
    rm = _ledger(10, 10, 0.0)
    ev = _Events()
    _emit_budget_status(rm, ev)
    assert ev.kinds() == ["budget_status"]
    assert not rm.get("adaptive_efficiency")


def test_emit_hard_cap_emits_budget_exhausted(clean_budget_env):
    clean_budget_env.setenv("AGENT_LAB_SESSION_TOKEN_BUDGET", "100")
    clean_budget_env.setenv("AGENT_LAB_SESSION_HARD_CAP", "1")
    rm = _ledger(80, 40, 0.0)
    ev = _Events()
    _emit_budget_status(rm, ev)
    assert "budget_exhausted" in ev.kinds()
    assert rm["budget_exhausted"] is True


def test_emit_noop_without_on_event(clean_budget_env):
    rm = _ledger(5, 5, 0.0)
    _emit_budget_status(rm, None)  # must not raise
    assert "budget_status" not in rm  # nothing emitted, snapshot only set when on_event present


def test_session_hard_cap_enabled_env(clean_budget_env):
    assert _session_hard_cap_enabled() is False
    clean_budget_env.setenv("AGENT_LAB_SESSION_HARD_CAP", "1")
    assert _session_hard_cap_enabled() is True


# --- run.json roundtrip (next-turn flag survival) -------------------------


def test_run_json_roundtrip_persists_budget_keys(clean_budget_env, tmp_path: Path):
    from agent_lab.run_meta import persist_run_meta, read_run_meta, write_run_meta

    run = {"adaptive_efficiency": True, "budget_exhausted": True, "budget_status": {"over": True}}
    write_run_meta(tmp_path, persist_run_meta(run))
    back = read_run_meta(tmp_path)
    # adaptive_efficiency must survive to the next turn (drives effective_efficiency OR)
    assert back.get("adaptive_efficiency") is True
    assert back.get("budget_exhausted") is True
    assert back.get("budget_status", {}).get("over") is True


def test_effective_efficiency_or_contract():
    # the run_room/continue_room_round expression: efficiency_mode or adaptive flag
    def effective(efficiency_mode, run_meta):
        return efficiency_mode or bool((run_meta or {}).get("adaptive_efficiency"))

    assert effective(False, {"adaptive_efficiency": True}) is True
    assert effective(False, {}) is False
    assert effective(True, {}) is True


# --- hard-cap preflight helper --------------------------------------------


def test_session_hard_cap_exhausted_helper(clean_budget_env, tmp_path: Path):
    from app.server.routers.room import _session_hard_cap_exhausted

    (tmp_path / "run.json").write_text(json.dumps({"budget_exhausted": True}), encoding="utf-8")
    # env off -> never blocks
    assert _session_hard_cap_exhausted(tmp_path) is False
    # env on + exhausted -> blocks
    clean_budget_env.setenv("AGENT_LAB_SESSION_HARD_CAP", "1")
    assert _session_hard_cap_exhausted(tmp_path) is True
    # env on + not exhausted -> ok
    (tmp_path / "run.json").write_text(json.dumps({}), encoding="utf-8")
    assert _session_hard_cap_exhausted(tmp_path) is False


# --- regression: mission/USD budget_status untouched ----------------------


def test_budget_status_unchanged_for_mission(clean_budget_env):
    from agent_lab.cost_ledger import budget_status

    clean_budget_env.setenv("AGENT_LAB_MISSION_BUDGET_USD", "1.0")
    st = budget_status(_ledger(0, 0, 1.5))
    assert st["over"] is True and st["limit_usd"] == 1.0  # mission circuit-breaker path intact
