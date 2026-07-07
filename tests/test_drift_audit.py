"""C2 — L3 drift audit unit tests (mock-only, no real I/O beyond tmp_path).

docs/N10-USER-LOOP-WISDOM-DRAFT.md §4-C2.
"""

from __future__ import annotations

import json

from agent_lab.drift_audit import (
    handle_drift_audit_inbox_resolve,
    maybe_run_drift_audit,
    snapshot_drift_baseline,
    uncovered_actions,
)
from agent_lab.run.meta import read_run_meta

PLAN_MD = """## 지금 실행
1.
   - 무엇을: implement auth middleware.
   - 어디서: `src/auth.py`
   - 검증: pytest tests/test_auth.py
   (ref: chat.jsonl#L1)

## 실행 순서 (이후)
2.
   - 무엇을: add rate limiting.
   - 어디서: `src/ratelimit.py`
   - 검증: pytest tests/test_ratelimit.py
   (ref: chat.jsonl#L2)
3.
   - 무엇을: add audit logging.
   - 어디서: `src/audit.py`
   - 검증: pytest tests/test_audit.py
   (ref: chat.jsonl#L3)
"""


def _write_session(folder, *, autonomous_active: bool = True, user_turns: int = 1) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "plan.md").write_text(PLAN_MD, encoding="utf-8")
    run = {
        "topic": "drift audit mission",
        "mission_loop": {"autonomous_segment": {"active": autonomous_active}},
        "executions": [],
    }
    (folder / "run.json").write_text(json.dumps(run), encoding="utf-8")
    lines = []
    for i in range(user_turns):
        lines.append(json.dumps({"role": "user", "agent": None, "content": f"turn {i + 1}"}))
        lines.append(json.dumps({"role": "agent", "agent": "cursor", "content": f"ack {i + 1}"}))
    (folder / "chat.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _patch_run(folder, **fields) -> None:
    run = json.loads((folder / "run.json").read_text(encoding="utf-8"))
    run.update(fields)
    (folder / "run.json").write_text(json.dumps(run), encoding="utf-8")


# --- snapshot_drift_baseline ------------------------------------------------


def test_snapshot_drift_baseline_writes_parsed_actions(tmp_path):
    _write_session(tmp_path)
    snapshot_drift_baseline(tmp_path, PLAN_MD, human_turn=1)
    baseline = read_run_meta(tmp_path).get("drift_baseline")
    assert baseline is not None
    assert baseline["human_turn"] == 1
    indices = sorted(a["index"] for a in baseline["actions"])
    assert indices == [1, 2, 3]


def test_snapshot_drift_baseline_fails_open_on_garbage_plan(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "run.json").write_text(json.dumps({"topic": "x"}), encoding="utf-8")
    snapshot_drift_baseline(tmp_path, "not a real plan format", human_turn=1)
    baseline = read_run_meta(tmp_path).get("drift_baseline")
    assert baseline is not None
    assert baseline["actions"] == []


# --- uncovered_actions (pure) ------------------------------------------------


def test_uncovered_actions_empty_without_baseline():
    assert uncovered_actions({}) == []


def test_uncovered_actions_flags_missing_indices():
    run_meta = {
        "drift_baseline": {
            "human_turn": 1,
            "actions": [{"index": 1, "what": "a"}, {"index": 2, "what": "b"}, {"index": 3, "what": "c"}],
        },
        "executions": [{"action_index": 1}],
    }
    missing = uncovered_actions(run_meta)
    assert sorted(a["index"] for a in missing) == [2, 3]


def test_uncovered_actions_empty_when_all_executed():
    run_meta = {
        "drift_baseline": {"human_turn": 1, "actions": [{"index": 1, "what": "a"}]},
        "executions": [{"action_index": 1}],
    }
    assert uncovered_actions(run_meta) == []


# --- maybe_run_drift_audit ---------------------------------------------------


def test_drift_audit_noop_without_baseline(tmp_path):
    _write_session(tmp_path)
    assert maybe_run_drift_audit(tmp_path, 10) is None
    assert not (read_run_meta(tmp_path).get("human_inbox") or [])


def test_drift_audit_noop_when_not_autonomous(tmp_path):
    _write_session(tmp_path, autonomous_active=False)
    snapshot_drift_baseline(tmp_path, PLAN_MD, human_turn=1)
    assert maybe_run_drift_audit(tmp_path, 11) is None
    assert not (read_run_meta(tmp_path).get("human_inbox") or [])


def test_drift_audit_noop_before_interval_elapses(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_LAB_DRIFT_AUDIT_INTERVAL", "10")
    _write_session(tmp_path)
    snapshot_drift_baseline(tmp_path, PLAN_MD, human_turn=1)
    assert maybe_run_drift_audit(tmp_path, 5) is None
    assert not (read_run_meta(tmp_path).get("human_inbox") or [])


def test_drift_audit_noop_flag_off(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_LAB_DRIFT_AUDIT", "0")
    _write_session(tmp_path)
    snapshot_drift_baseline(tmp_path, PLAN_MD, human_turn=1)
    assert maybe_run_drift_audit(tmp_path, 11) is None


def test_drift_audit_escalates_at_interval_with_missing_actions(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_LAB_DRIFT_AUDIT_INTERVAL", "10")
    _write_session(tmp_path)
    snapshot_drift_baseline(tmp_path, PLAN_MD, human_turn=1)
    _patch_run(tmp_path, executions=[{"action_index": 1}])  # action 2, 3 uncovered

    item = maybe_run_drift_audit(tmp_path, 11)
    assert item is not None
    assert item["kind"] == "drift_audit"

    items = read_run_meta(tmp_path).get("human_inbox") or []
    assert len(items) == 1
    assert items[0]["refs"][0] == "1"
    assert set(items[0]["refs"][1:]) == {"2", "3"}


def test_drift_audit_noop_when_all_covered(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_LAB_DRIFT_AUDIT_INTERVAL", "10")
    _write_session(tmp_path)
    snapshot_drift_baseline(tmp_path, PLAN_MD, human_turn=1)
    _patch_run(tmp_path, executions=[{"action_index": 1}, {"action_index": 2}, {"action_index": 3}])

    assert maybe_run_drift_audit(tmp_path, 11) is None
    assert not (read_run_meta(tmp_path).get("human_inbox") or [])


def test_drift_audit_does_not_duplicate_pending_escalation(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_LAB_DRIFT_AUDIT_INTERVAL", "10")
    _write_session(tmp_path)
    snapshot_drift_baseline(tmp_path, PLAN_MD, human_turn=1)
    _patch_run(tmp_path, executions=[{"action_index": 1}])

    first = maybe_run_drift_audit(tmp_path, 11)
    second = maybe_run_drift_audit(tmp_path, 21)  # next interval boundary, still pending
    assert first is not None
    assert second is None
    assert len(read_run_meta(tmp_path).get("human_inbox") or []) == 1


# --- handle_drift_audit_inbox_resolve ----------------------------------------


def test_drift_audit_reground_resnapshots_baseline_at_current_turn(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_LAB_DRIFT_AUDIT_INTERVAL", "10")
    _write_session(tmp_path, user_turns=3)
    snapshot_drift_baseline(tmp_path, PLAN_MD, human_turn=1)
    _patch_run(tmp_path, executions=[{"action_index": 1}])

    item = maybe_run_drift_audit(tmp_path, 11)
    assert item is not None

    handle_drift_audit_inbox_resolve(tmp_path, item, selected=["reground"], status="resolved")

    baseline = read_run_meta(tmp_path).get("drift_baseline")
    assert baseline["human_turn"] == 3  # re-grounded to current turn count from chat.jsonl


def test_drift_audit_split_does_not_resnapshot(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_LAB_DRIFT_AUDIT_INTERVAL", "10")
    _write_session(tmp_path, user_turns=3)
    snapshot_drift_baseline(tmp_path, PLAN_MD, human_turn=1)
    _patch_run(tmp_path, executions=[{"action_index": 1}])

    item = maybe_run_drift_audit(tmp_path, 11)
    assert item is not None

    handle_drift_audit_inbox_resolve(tmp_path, item, selected=["split"], status="resolved")

    baseline = read_run_meta(tmp_path).get("drift_baseline")
    assert baseline["human_turn"] == 1  # unchanged


def test_drift_audit_reject_does_not_resnapshot(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_LAB_DRIFT_AUDIT_INTERVAL", "10")
    _write_session(tmp_path, user_turns=3)
    snapshot_drift_baseline(tmp_path, PLAN_MD, human_turn=1)
    _patch_run(tmp_path, executions=[{"action_index": 1}])

    item = maybe_run_drift_audit(tmp_path, 11)
    assert item is not None

    handle_drift_audit_inbox_resolve(tmp_path, item, selected=["reground"], status="rejected")

    baseline = read_run_meta(tmp_path).get("drift_baseline")
    assert baseline["human_turn"] == 1  # rejected resolve is a no-op
