"""task_type-based parallel gate (Fix C).

Key invariant: run_parallel_round calls team_r1_split in two places:
  1. _round_agent_order (always, for ordering) — 1 call
  2. the ternary that builds parallel_batch/lead_tail — only when NOT sequential

So the total call count of team_r1_split distinguishes the code paths:
  - sequential task types (peer_review, cold_critic): exactly 1 call
  - parallel task types (consensus, discuss, None): 2 calls (ordering + batch split)
"""

from __future__ import annotations

from typing import Any

import pytest

from agent_mocks import patch_call_agent_reply


def _make_run_meta(tmp_path: Any) -> dict[str, Any]:
    from agent_lab.run.meta import write_run_meta

    folder = tmp_path / "sess"
    folder.mkdir()
    (folder / "topic.txt").write_text("topic\n")
    write_run_meta(folder, {})
    return {
        "_session_folder": str(folder),
        "_active_turn_mode": "discuss",
        "_active_synthesize": False,
        "_active_consensus": False,
    }


def _fake_agent_fn(agent: str, _s: str, _u: str, **_kw: Any) -> str:
    return f"reply-{agent}"


def _run_with_split_counter(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
    *,
    task_type: str | None,
    agents: list[str],
) -> int:
    """Run one round and return the number of team_r1_split calls."""
    from agent_lab import room
    from agent_lab.room.team_orchestration import team_r1_split as _real_split

    run_meta = _make_run_meta(tmp_path)
    split_calls: list[Any] = []

    def counting_split(agent_list: Any, meta: Any) -> tuple[list, list]:
        split_calls.append(list(agent_list))
        return _real_split(agent_list, meta)  # real fn captured before patching

    monkeypatch.setattr(
        "agent_lab.room.team_orchestration.team_r1_split",
        counting_split,
    )
    patch_call_agent_reply(monkeypatch, _fake_agent_fn)
    monkeypatch.setattr(room, "model_label", lambda a: f"{a}-model")

    messages = [room.ChatMessage(role="user", agent=None, content="prompt")]
    room.run_parallel_round(
        "topic",
        messages,
        agents=agents,  # type: ignore[arg-type]
        parallel_round=1,
        run_meta=run_meta,
        task_type=task_type,
    )
    return len(split_calls)


def test_sequential_task_types_constant() -> None:
    """peer_review and cold_critic are sequential; consensus and discuss are not."""
    from agent_lab.room.parallel_rounds import _SEQUENTIAL_TASK_TYPES

    assert "peer_review" in _SEQUENTIAL_TASK_TYPES
    assert "cold_critic" in _SEQUENTIAL_TASK_TYPES
    assert "consensus" not in _SEQUENTIAL_TASK_TYPES
    assert "discuss" not in _SEQUENTIAL_TASK_TYPES


def test_peer_review_sequential_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    """peer_review skips the parallel batch split — only the ordering call remains."""
    n = _run_with_split_counter(monkeypatch, tmp_path, task_type="peer_review", agents=["cursor", "claude"])
    assert n == 1, f"peer_review: expected 1 team_r1_split call (ordering only), got {n}"


def test_cold_critic_sequential_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    """cold_critic also skips the parallel batch split."""
    n = _run_with_split_counter(monkeypatch, tmp_path, task_type="cold_critic", agents=["claude"])
    assert n == 1, f"cold_critic: expected 1 team_r1_split call (ordering only), got {n}"


def test_consensus_parallel_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    """consensus goes through the parallel batch split (ordering + lead-last split)."""
    n = _run_with_split_counter(monkeypatch, tmp_path, task_type="consensus", agents=["cursor", "claude"])
    assert n == 2, f"consensus: expected 2 team_r1_split calls (ordering + batch split), got {n}"


def test_no_task_type_parallel_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    """Omitting task_type preserves round-1 parallel behaviour."""
    n = _run_with_split_counter(monkeypatch, tmp_path, task_type=None, agents=["cursor", "claude"])
    assert n == 2, f"no task_type: expected 2 team_r1_split calls (backward-compat parallel), got {n}"
