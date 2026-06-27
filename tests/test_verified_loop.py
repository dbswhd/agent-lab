"""Verified loop (LazyCodex-style) state machine tests."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from agent_lab.run_meta import read_run_meta
from agent_lab.session_guidance import SESSION_META_KEYS, preserve_session_meta_from_prev
from agent_lab.verified_loop import (
    approve_verified_loop,
    detect_completion_promise,
    harvest_all_proposals,
    harvest_proposal,
    init_verified_loop,
    is_oracle_verified,
    maybe_handle_verified_loop_after_turn,
    merge_proposals,
    record_proposed_goal,
    run_verified_oracle,
)
from agent_lab.verified_loop import _loop_work_prompt


def _verified_oracle_output(session_id: str) -> str:
    return (
        "Agent: oracle\n"
        "<promise>VERIFIED</promise>\n"
        f"<task_metadata>\n"
        f"session_id: {session_id}\n"
        "</task_metadata>\n"
        "Evidence supports the loop goal."
    )


def _session(tmp_path: Path) -> Path:
    folder = tmp_path / "sess-verified"
    folder.mkdir()
    (folder / "topic.txt").write_text("Build auth middleware\n", encoding="utf-8")
    (folder / "run.json").write_text("{}\n", encoding="utf-8")
    return folder


def test_harvest_ulw_proposal_envelope() -> None:
    text = """
    Team view:
    <ulw_proposal>
    goal: Add JWT middleware
    completion_promise: DONE
    criteria: Tests pass and middleware wired
    </ulw_proposal>
    """
    proposal = harvest_proposal([{"role": "agent", "content": text}])
    assert proposal is not None
    assert proposal["goal"] == "Add JWT middleware"
    assert proposal["completion_promise"] == "DONE"


def test_proposing_turn_sets_pending_approval(tmp_path: Path) -> None:
    folder = _session(tmp_path)
    messages = [
        {
            "role": "agent",
            "content": (
                "<ulw_proposal>\n"
                "goal: Ship feature X\n"
                "completion_promise: DONE\n"
                "criteria: Feature X documented\n"
                "</ulw_proposal>"
            ),
        }
    ]
    result = maybe_handle_verified_loop_after_turn(folder, messages, "verified")
    assert result is not None
    assert result["verified_loop_pending"] is True
    run = read_run_meta(folder)
    assert run["verified_loop"]["status"] == "pending_approval"
    assert run["session_goal"]["set_by"] == "agents"


def test_approve_starts_running_state(tmp_path: Path) -> None:
    folder = _session(tmp_path)
    record_proposed_goal(
        folder,
        {
            "goal": "Finish docs",
            "completion_promise": "DONE",
            "criteria": "README updated",
        },
    )
    out = approve_verified_loop(folder)
    assert out["verified_loop"]["status"] == "running"
    assert out["continue_prompt"]
    assert "Finish docs" in out["continue_prompt"]


def test_oracle_verified_two_phase_exit(tmp_path: Path) -> None:
    folder = _session(tmp_path)
    record_proposed_goal(
        folder,
        {
            "goal": "Include `READY` in answer",
            "completion_promise": "DONE",
            "criteria": "Transcript contains READY",
        },
    )
    approve_verified_loop(folder)
    run = read_run_meta(folder)
    oracle_session_id = run["verified_loop"]["oracle_session_id"]

    messages = [
        {"role": "agent", "content": "Work done.\n<promise>DONE</promise>"},
    ]

    def oracle_ok(_prompt: str) -> str:
        return _verified_oracle_output(oracle_session_id)

    result = maybe_handle_verified_loop_after_turn(
        folder,
        messages,
        "verified",
        oracle_call=oracle_ok,
    )
    assert result is not None
    assert result["verified_loop"]["status"] == "done"
    assert result["check"]["verdict"] == "verified"


def test_oracle_fail_increments_verification_attempts(tmp_path: Path) -> None:
    folder = _session(tmp_path)
    record_proposed_goal(
        folder,
        {
            "goal": "Include `READY`",
            "completion_promise": "DONE",
            "criteria": "READY present",
        },
    )
    approve_verified_loop(folder)
    messages = [{"role": "agent", "content": "<promise>DONE</promise>"}]

    result = maybe_handle_verified_loop_after_turn(
        folder,
        messages,
        "verified",
        oracle_call=lambda _p: "FAIL: READY missing",
    )
    assert result is not None
    loop = result["verified_loop"]
    assert loop["status"] == "running"
    assert loop["verification_attempts"] == 1
    assert result.get("continue_prompt")


def test_circuit_breaker_after_max_verification_attempts(tmp_path: Path) -> None:
    folder = _session(tmp_path)
    record_proposed_goal(
        folder,
        {
            "goal": "Include `READY`",
            "completion_promise": "DONE",
            "criteria": "READY present",
        },
    )
    approve_verified_loop(folder)
    messages = [{"role": "agent", "content": "<promise>DONE</promise>"}]

    def oracle_fail(_p):
        return "FAIL: still missing"

    for _ in range(3):
        maybe_handle_verified_loop_after_turn(
            folder,
            messages,
            "verified",
            oracle_call=oracle_fail,
        )

    run = read_run_meta(folder)
    assert run["verified_loop"]["status"] == "failed"
    assert run["verified_loop"]["circuit_breaker"] is True


def test_detect_completion_promise_ignores_verified_spoof() -> None:
    messages = [
        {
            "role": "agent",
            "content": "<promise>VERIFIED</promise>",
        }
    ]
    assert detect_completion_promise(messages, "DONE") is False
    assert detect_completion_promise(
        [{"role": "agent", "content": "<promise>DONE</promise>"}],
        "DONE",
    )


def test_is_oracle_verified_requires_structured_block() -> None:
    assert is_oracle_verified("PASS: ok") is False
    assert is_oracle_verified(
        "Agent: oracle\n<promise>VERIFIED</promise>\nreason",
        oracle_session_id="oracle_sess_abc",
    )


def test_init_verified_loop_idempotent(tmp_path: Path) -> None:
    folder = _session(tmp_path)
    first = init_verified_loop(folder)
    second = init_verified_loop(folder)
    assert first["status"] == "proposing"
    assert second["status"] == "proposing"


def test_run_verified_oracle_inject_path(tmp_path: Path) -> None:
    folder = _session(tmp_path)
    init_verified_loop(folder)
    patch = run_verified_oracle(
        folder,
        goal_text="goal",
        criteria="criteria",
        completion_promise="DONE",
        messages_snapshot=[{"role": "agent", "content": "done"}],
        oracle_call=lambda _p: _verified_oracle_output("oracle_x"),
    )
    assert patch["verdict"] == "verified"
    assert patch["source"] == "inject"


def test_merge_multiple_ulw_proposals() -> None:
    messages = [
        {
            "role": "agent",
            "agent": "cursor",
            "content": (
                "<ulw_proposal>\n"
                "goal: End-to-end smoke\n"
                "completion_promise: DONE\n"
                "criteria: Oracle VERIFIED in run.json\n"
                "</ulw_proposal>"
            ),
        },
        {
            "role": "agent",
            "agent": "codex",
            "content": (
                "<ulw_proposal>\n"
                "goal: Attachment path only\n"
                "completion_promise: DONE\n"
                "criteria: IMG file 38764 bytes on disk\n"
                "</ulw_proposal>"
            ),
        },
    ]
    merged = merge_proposals(harvest_all_proposals(messages))
    assert merged is not None
    assert merged["goal"] == "End-to-end smoke"
    assert "Oracle VERIFIED" in merged["criteria"]
    assert "38764 bytes" in merged["criteria"]
    assert merged.get("merged_from") == 2


def test_cancelled_turn_preserves_running_state(tmp_path: Path) -> None:
    folder = _session(tmp_path)
    record_proposed_goal(
        folder,
        {
            "goal": "Ship it",
            "completion_promise": "DONE",
            "criteria": "README has READY",
        },
    )
    approve_verified_loop(folder)
    run_before = read_run_meta(folder)
    assert run_before["verified_loop"]["status"] == "running"
    assert run_before["verified_loop"].get("loop_goal")

    result = maybe_handle_verified_loop_after_turn(
        folder,
        [{"role": "agent", "content": "<ulw_proposal>\ngoal: Hijack\n</ulw_proposal>"}],
        "verified",
        cancelled=True,
    )
    assert result is not None
    assert result.get("cancelled") is True
    run_after = read_run_meta(folder)
    assert run_after["verified_loop"]["status"] == "running"
    assert run_after["verified_loop"].get("loop_goal")
    assert run_after["verified_loop"].get("loop_goal") == run_before["verified_loop"]["loop_goal"]


def test_approve_keeps_rich_proposed_criteria_when_body_collapsed(tmp_path: Path) -> None:
    folder = _session(tmp_path)
    record_proposed_goal(
        folder,
        {
            "goal": "Short goal",
            "completion_promise": "DONE",
            "criteria": "(1) disk file exists (2) chat.jsonl meta (3) DONE promise",
        },
    )
    out = approve_verified_loop(folder, goal="Short goal", criteria="Short goal")
    criteria = out["verified_loop"]["loop_goal"]["criteria"]
    assert "chat.jsonl" in criteria
    assert criteria != "Short goal"


def test_loop_work_prompt_shows_distinct_criteria() -> None:
    prompt = _loop_work_prompt(
        {
            "loop_goal": {
                "text": "Smoke test",
                "completion_promise": "DONE",
                "criteria": "(1) file on disk (2) DONE emitted",
            }
        }
    )
    assert "Goal: Smoke test" in prompt
    assert "Criteria:\n(1) file on disk" in prompt
    assert "Criteria: Smoke test" not in prompt


def test_session_meta_preserves_verified_loop() -> None:
    assert "verified_loop" in SESSION_META_KEYS
    run_meta: dict = {"topic": "t", "last_turn": {}}
    prev = {
        "verified_loop": {
            "status": "running",
            "loop_goal": {
                "text": "Ship feature",
                "approved_at": "2026-05-30T12:00:00+00:00",
            },
        }
    }
    preserve_session_meta_from_prev(run_meta, prev)
    assert run_meta["verified_loop"]["status"] == "running"
    assert run_meta["verified_loop"]["loop_goal"]["text"] == "Ship feature"


def test_session_meta_preserves_mission_loop() -> None:
    assert "mission_loop" in SESSION_META_KEYS
    run_meta: dict = {"topic": "t", "last_turn": {}}
    prev = {
        "mission_loop": {
            "enabled": True,
            "phase": "DISCUSS",
            "pending_action_indices": [1],
        },
        "mission_board": {"goal_chain": [{"text": "Ship"}]},
        "turn_budget": {"used": 2, "limit": 12},
    }
    preserve_session_meta_from_prev(run_meta, prev)
    assert run_meta["mission_loop"]["phase"] == "DISCUSS"
    assert run_meta["mission_board"]["goal_chain"][0]["text"] == "Ship"
    assert run_meta["turn_budget"]["used"] == 2


def test_stale_done_before_approval_ignored(tmp_path: Path) -> None:
    folder = _session(tmp_path)
    record_proposed_goal(
        folder,
        {
            "goal": "Include READY",
            "completion_promise": "DONE",
            "criteria": "READY present",
        },
    )
    out = approve_verified_loop(folder)
    approved_at = out["verified_loop"]["loop_goal"]["approved_at"]
    cutoff = datetime.fromisoformat(approved_at.replace("Z", "+00:00"))
    before = (cutoff - timedelta(minutes=5)).isoformat()
    after = (cutoff + timedelta(minutes=5)).isoformat()
    oracle_session_id = out["verified_loop"]["oracle_session_id"]

    stale_messages = [
        {"role": "agent", "content": "<promise>DONE</promise>", "ts": before},
    ]
    result = maybe_handle_verified_loop_after_turn(
        folder,
        stale_messages,
        "verified",
        oracle_call=lambda _p: _verified_oracle_output(oracle_session_id),
    )
    assert result is not None
    assert result["verified_loop"]["status"] == "running"
    assert result.get("continue_prompt")

    fresh_messages = stale_messages + [
        {"role": "agent", "content": "READY is in the transcript.", "ts": after},
        {"role": "agent", "content": "<promise>DONE</promise>", "ts": after},
    ]
    result2 = maybe_handle_verified_loop_after_turn(
        folder,
        fresh_messages,
        "verified",
        oracle_call=lambda _p: _verified_oracle_output(oracle_session_id),
    )
    assert result2 is not None
    assert result2["verified_loop"]["status"] == "done"
    assert result2["check"]["verdict"] == "verified"


def test_detect_completion_promise_since_iso_filters_messages() -> None:
    since = "2026-05-30T12:00:00+00:00"
    before = "2026-05-30T11:00:00+00:00"
    after = "2026-05-30T13:00:00+00:00"
    messages = [
        {"role": "agent", "content": "<promise>DONE</promise>", "ts": before},
        {"role": "agent", "content": "no promise here", "ts": after},
    ]
    assert detect_completion_promise(messages, "DONE", since_iso=since) is False
    messages.append(
        {"role": "agent", "content": "<promise>DONE</promise>", "ts": after},
    )
    assert detect_completion_promise(messages, "DONE", since_iso=since) is True


def test_maybe_auto_scribe_after_verified_loop_harvests_inbox(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AGENT_LAB_ORCHESTRATOR_INBOX_HARVEST", "1")
    from agent_lab.room import maybe_auto_scribe_after_verified_loop

    folder = _session(tmp_path)
    (folder / "chat.jsonl").write_text(
        '{"role":"user","content":"Build auth"}\n',
        encoding="utf-8",
    )
    verified_at = "2026-06-07T04:44:45+00:00"
    plan_md = """\
## 합의

- Verified goal captured

## 지금 실행

1. JWT middleware 추가
   - 무엇을: `auth/jwt.py` 추가
   - 어디서: `src/auth/`
   - 검증: `pytest tests/test_jwt.py`
"""
    monkeypatch.setattr(
        "agent_lab.room.synthesize_session_plan",
        lambda *_a, **_k: (plan_md, "plan synced"),
    )
    events: list[tuple[str, dict]] = []

    def on_event(name: str, payload: dict) -> None:
        events.append((name, payload))

    verified_result = {
        "verified_loop": {
            "status": "done",
            "verified_at": verified_at,
            "loop_goal": {"text": "Add JWT middleware", "criteria": "tests pass"},
        }
    }
    result = maybe_auto_scribe_after_verified_loop(
        folder,
        verified_result=verified_result,
        cancelled=False,
        on_event=on_event,
    )
    assert result == plan_md
    run = read_run_meta(folder)
    assert run["verified_plan_sync"]["verified_at"] == verified_at
    builds = [i for i in run.get("human_inbox", []) if i.get("kind") == "build"]
    assert len(builds) == 1
    assert builds[0]["action_ref"] == "now:1"
    assert any(e[0] == "verified_plan_synced" for e in events)
    assert any(e[0] == "consensus_dry_run_proposal" for e in events)

    # idempotent
    again = maybe_auto_scribe_after_verified_loop(
        folder,
        verified_result=verified_result,
        cancelled=False,
    )
    assert again is None
