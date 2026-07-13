from __future__ import annotations

from pathlib import Path

import pytest

from agent_lab.mission.kernel import (
    ApproveDiff,
    ApprovePlan,
    MarkDiffReady,
    OpenPlan,
    OracleVerdict,
    RecordMerge,
    RecordOracle,
    RejectPlan,
    StartExecution,
    MissionCommand,
    MissionState,
    MissionTransitionError,
)
from agent_lab.mission.plan_bridge import PlanApprovalDecision
from agent_lab.mission.repository import MissionRepository


def test_repository_appends_events_and_replays_state(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    repository = MissionRepository(path, "m-1", "ship it")

    opened = repository.dispatch(OpenPlan("hash-a"))
    approved = repository.dispatch(ApprovePlan("hash-a"), expected_version=opened.version)

    restored = MissionRepository(path, "m-1", "ship it")

    assert approved.state is MissionState.READY_TO_EXECUTE
    assert approved.version == 2
    assert restored.load() == approved


def test_repository_plan_decision_binds_plan_content_hash(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    repository = MissionRepository(path, "m-7", "plan")

    approved = repository.decide_plan("# Plan\n\n- do it", PlanApprovalDecision(True))

    assert approved.state is MissionState.READY_TO_EXECUTE
    assert approved.approved_plan_hash is not None
    assert MissionRepository(path, "m-7", "plan").load() == approved
    assert len(path.read_text(encoding="utf-8").splitlines()) == 1


def test_repository_rejection_reopens_for_new_revision(tmp_path: Path) -> None:
    repository = MissionRepository(tmp_path / "events.jsonl", "m-2", "revise")

    repository.dispatch(OpenPlan("hash-a"))
    rejected = repository.dispatch(RejectPlan("needs work"))
    reopened = repository.dispatch(OpenPlan("hash-b"))
    approved = repository.dispatch(ApprovePlan("hash-b"))

    assert rejected.state is MissionState.DRAFTING
    assert reopened.plan_revision == 2
    assert approved.approved_plan_hash == "hash-b"


def test_repository_rejects_stale_writer(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    first = MissionRepository(path, "m-3", "race")
    second = MissionRepository(path, "m-3", "race")

    first.dispatch(OpenPlan("hash-a"))

    with pytest.raises(MissionTransitionError):
        second.dispatch(OpenPlan("hash-b"), expected_version=0)


def test_repository_dispatch_is_durable_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    first_repository = MissionRepository(path, "m-3-idempotent", "retry")
    first = first_repository.dispatch(OpenPlan("hash-a"), idempotency_key="open-hash-a")

    restarted = MissionRepository(path, "m-3-idempotent", "retry")
    second = restarted.dispatch(OpenPlan("hash-a"), expected_version=0, idempotency_key="open-hash-a")

    assert second == first
    assert second.version == 1
    assert len(restarted._journal.load()) == 1


def test_repository_exec_merge_oracle_pass_survives_restart(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    repository = MissionRepository(path, "m-4", "ship it")

    for command in (
        OpenPlan("hash-a"),
        ApprovePlan("hash-a"),
        StartExecution(),
        MarkDiffReady(),
        ApproveDiff(),
        RecordMerge("sha-a"),
        RecordOracle(OracleVerdict.PASS, "all checks green"),
    ):
        repository.dispatch(command)

    restored = MissionRepository(path, "m-4", "ship it").load()

    assert restored.state is MissionState.SUCCEEDED
    assert restored.merged_commit_sha == "sha-a"


def test_repository_oracle_failure_requires_repair_merge_before_pass(tmp_path: Path) -> None:
    repository = MissionRepository(tmp_path / "events.jsonl", "m-5", "repair it")

    for command in (
        OpenPlan("hash-a"),
        ApprovePlan("hash-a"),
        StartExecution(),
        MarkDiffReady(),
        ApproveDiff(),
        RecordMerge("sha-a"),
    ):
        repository.dispatch(command)
    failed = repository.dispatch(RecordOracle(OracleVerdict.FAIL, "missing evidence"))
    assert failed.state is MissionState.REPAIRING

    for command in (MarkDiffReady(), ApproveDiff()):
        repository.dispatch(command)
    with pytest.raises(MissionTransitionError, match="merge must be recorded"):
        repository.dispatch(RecordOracle(OracleVerdict.PASS, "not yet"))

    commands: tuple[MissionCommand, ...] = (RecordMerge("sha-b"), RecordOracle(OracleVerdict.PASS, "fixed"))
    for next_command in commands:
        repository.dispatch(next_command)

    assert repository.load().state is MissionState.SUCCEEDED


def test_repository_recovers_after_daemon_crash_during_append(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    repository = MissionRepository(path, "m-6", "recover")
    repository.dispatch(OpenPlan("hash-a"))
    with path.open("ab") as stream:
        stream.write(b'{"sequence":2')

    restored = MissionRepository(path, "m-6", "recover").load()

    assert restored.state is MissionState.AWAITING_PLAN_DECISION
    assert restored.version == 1
