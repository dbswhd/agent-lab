from __future__ import annotations

import json
import multiprocessing
from pathlib import Path

import pytest

from agent_lab.mission.journal import (
    JournalConflictError,
    JournalCorruptionError,
    JournalIdempotencyError,
    MissionJournal,
    PendingEvent,
)


def _append_from_process(path_text: str, queue: multiprocessing.Queue[str]) -> None:
    journal = MissionJournal(Path(path_text))
    try:
        journal.append((PendingEvent("PlanOpened", {"hash": "abc"}),), expected_sequence=0)
    except JournalConflictError:
        queue.put("conflict")
    else:
        queue.put("ok")


def test_journal_appends_monotonic_sequences_and_replays(tmp_path: Path) -> None:
    journal = MissionJournal(tmp_path / "events.jsonl")
    stored = journal.append((PendingEvent("PlanOpened", {"hash": "abc"}),), expected_sequence=0)
    stored += journal.append((PendingEvent("PlanApproved", {"hash": "abc"}),), expected_sequence=1)
    assert [event.sequence for event in stored] == [1, 2]
    assert [event.event_type for event in journal.load()] == ["PlanOpened", "PlanApproved"]


def test_journal_rejects_stale_writer(tmp_path: Path) -> None:
    journal = MissionJournal(tmp_path / "events.jsonl")
    journal.append((PendingEvent("PlanOpened", {}),), expected_sequence=0)
    with pytest.raises(JournalConflictError):
        journal.append((PendingEvent("PlanApproved", {}),), expected_sequence=0)


def test_journal_recovers_incomplete_tail(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    journal = MissionJournal(path)
    journal.append((PendingEvent("PlanOpened", {}),), expected_sequence=0)
    with path.open("ab") as stream:
        stream.write(b'{"sequence":2')
    recovered = journal.recover_tail()
    assert [event.sequence for event in recovered] == [1]
    assert json.loads(path.read_text(encoding="utf-8").splitlines()[0])["sequence"] == 1
    assert journal.lock_path.is_file()


def test_journal_stores_multi_event_append_as_one_atomic_record(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    journal = MissionJournal(path, mission_id="mission-batch")

    stored = journal.append(
        (
            PendingEvent("PlanOpened", {"hash": "abc"}),
            PendingEvent("PlanApproved", {"hash": "abc"}),
        ),
        expected_sequence=0,
    )

    assert [event.sequence for event in stored] == [1, 2]
    assert [event.sequence for event in journal.load()] == [1, 2]
    record = json.loads(path.read_text(encoding="utf-8"))
    assert record["record_type"] == "batch"
    assert len(record["events"]) == 2


def test_journal_recovers_incomplete_batch_record(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    journal = MissionJournal(path)
    journal.append((PendingEvent("PlanOpened", {}),), expected_sequence=0)
    with path.open("ab") as stream:
        stream.write(b'{"record_type":"batch","batch_id":"b-1","events":[')

    recovered = journal.recover_tail()

    assert [event.sequence for event in recovered] == [1]
    assert len(path.read_text(encoding="utf-8").splitlines()) == 1


def test_journal_raises_for_corruption_before_tail(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    path.write_text("not-json\n{}\n", encoding="utf-8")
    with pytest.raises(JournalCorruptionError):
        MissionJournal(path).recover_tail()


def test_journal_rejects_non_monotonic_sequence(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    path.write_text(
        '{"event_id":"evt-1","sequence":1,"event_type":"PlanOpened","payload":{}}\n'
        '{"event_id":"evt-2","sequence":1,"event_type":"PlanApproved","payload":{}}\n',
        encoding="utf-8",
    )

    with pytest.raises(JournalCorruptionError, match="sequence"):
        MissionJournal(path).recover_tail()


def test_journal_does_not_hide_complete_malformed_tail(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    path.write_text("not-json\n", encoding="utf-8")

    with pytest.raises(JournalCorruptionError):
        MissionJournal(path).recover_tail()


def test_journal_creates_cross_process_lock_file(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    journal = MissionJournal(path)

    journal.append((PendingEvent("PlanOpened", {}),), expected_sequence=0)

    assert path.with_suffix(".jsonl.lock").is_file()


def test_journal_serializes_cross_process_append(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    context = multiprocessing.get_context("spawn")
    queue = context.Queue()
    processes = [context.Process(target=_append_from_process, args=(str(path), queue)) for _ in range(2)]
    for process in processes:
        process.start()
    for process in processes:
        process.join(timeout=10)

    assert all(process.exitcode == 0 for process in processes)
    assert sorted(queue.get(timeout=2) for _ in processes) == ["conflict", "ok"]
    assert len(MissionJournal(path).load()) == 1


def test_journal_replays_idempotent_append_without_duplicate(tmp_path: Path) -> None:
    journal = MissionJournal(tmp_path / "events.jsonl")
    first = journal.append(
        (PendingEvent("PlanOpened", {"hash": "abc"}),),
        expected_sequence=0,
        idempotency_key="open-abc",
    )
    second = journal.append(
        (PendingEvent("PlanOpened", {"hash": "abc"}),),
        expected_sequence=0,
        idempotency_key="open-abc",
    )

    assert second == first
    assert len(journal.load()) == 1
    assert journal.find_idempotency("open-abc") == first


def test_journal_rejects_reuse_with_different_payload(tmp_path: Path) -> None:
    journal = MissionJournal(tmp_path / "events.jsonl")
    journal.append(
        (PendingEvent("PlanOpened", {"hash": "abc"}),),
        expected_sequence=0,
        idempotency_key="open-abc",
    )

    with pytest.raises(JournalIdempotencyError):
        journal.append(
            (PendingEvent("PlanOpened", {"hash": "other"}),),
            expected_sequence=0,
            idempotency_key="open-abc",
        )


def test_journal_persists_and_validates_mission_identity(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    MissionJournal(path, mission_id="mission-a").append(
        (PendingEvent("PlanOpened", {}),),
        expected_sequence=0,
    )

    assert MissionJournal(path, mission_id="mission-a").load()[0].mission_id == "mission-a"
    with pytest.raises(JournalCorruptionError, match="mission_id"):
        MissionJournal(path, mission_id="mission-b").load()
