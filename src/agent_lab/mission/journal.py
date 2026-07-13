from __future__ import annotations

import json
import os
import threading
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Iterator
from typing import Any, Mapping

import fcntl

from agent_lab.mission.messages import JsonValue

_JOURNAL_LOCK = threading.Lock()


class JournalConflictError(Exception):
    def __init__(self, expected: int, actual: int) -> None:
        self.expected = expected
        self.actual = actual
        super().__init__(expected, actual)

    def __str__(self) -> str:
        return f"journal version conflict: expected {self.expected}, got {self.actual}"


class JournalIdempotencyError(Exception):
    def __init__(self, key: str, reason: str) -> None:
        self.key = key
        self.reason = reason
        super().__init__(key, reason)

    def __str__(self) -> str:
        return f"journal idempotency conflict for {self.key}: {self.reason}"


class JournalCorruptionError(Exception):
    def __init__(self, line_number: int, reason: str) -> None:
        self.line_number = line_number
        self.reason = reason
        super().__init__(line_number, reason)

    def __str__(self) -> str:
        return f"journal corruption at line {self.line_number}: {self.reason}"


@dataclass(frozen=True, slots=True)
class PendingEvent:
    event_type: str
    payload: Mapping[str, JsonValue]
    event_id: str | None = None


@dataclass(frozen=True, slots=True)
class StoredEvent:
    event_id: str
    sequence: int
    event_type: str
    payload: Mapping[str, JsonValue]
    idempotency_key: str | None = None
    mission_id: str | None = None
    schema_version: int = 1


def _decode_event(raw: Any, line_number: int) -> StoredEvent:
    if not isinstance(raw, dict):
        raise JournalCorruptionError(line_number, "event must be an object")
    sequence = raw.get("sequence")
    event_id = raw.get("event_id")
    event_type = raw.get("event_type")
    payload = raw.get("payload")
    idempotency_key = raw.get("idempotency_key")
    mission_id = raw.get("mission_id")
    schema_version = raw.get("schema_version", 1)
    if not isinstance(sequence, int) or isinstance(sequence, bool):
        raise JournalCorruptionError(line_number, "sequence must be an integer")
    if not isinstance(event_id, str) or not isinstance(event_type, str):
        raise JournalCorruptionError(line_number, "event identity is invalid")
    if not isinstance(payload, dict):
        raise JournalCorruptionError(line_number, "payload must be an object")
    if idempotency_key is not None and not isinstance(idempotency_key, str):
        raise JournalCorruptionError(line_number, "idempotency_key must be text")
    if mission_id is not None and not isinstance(mission_id, str):
        raise JournalCorruptionError(line_number, "mission_id must be text")
    if not isinstance(schema_version, int) or isinstance(schema_version, bool):
        raise JournalCorruptionError(line_number, "schema_version must be an integer")
    return StoredEvent(sequence=sequence, event_id=event_id, event_type=event_type, payload=payload, idempotency_key=idempotency_key, mission_id=mission_id, schema_version=schema_version)


def _decode_record(line: bytes, line_number: int) -> tuple[StoredEvent, ...]:
    try:
        raw: Any = json.loads(line.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise JournalCorruptionError(line_number, str(exc)) from exc
    if not isinstance(raw, dict):
        raise JournalCorruptionError(line_number, "record must be an object")
    if raw.get("record_type") != "batch":
        return (_decode_event(raw, line_number),)
    batch_id = raw.get("batch_id")
    events = raw.get("events")
    if not isinstance(batch_id, str) or not batch_id:
        raise JournalCorruptionError(line_number, "batch_id must be text")
    if not isinstance(events, list) or not events:
        raise JournalCorruptionError(line_number, "batch events must be a non-empty list")
    return tuple(_decode_event(event, line_number) for event in events)


class MissionJournal:
    def __init__(self, path: Path, *, mission_id: str | None = None, schema_version: int = 1) -> None:
        self.path = path
        self.mission_id = mission_id
        self.schema_version = schema_version

    def _validate_identity(self, event: StoredEvent, line_number: int) -> None:
        if self.mission_id is not None and event.mission_id not in (None, self.mission_id):
            raise JournalCorruptionError(line_number, "mission_id does not match journal")
        if event.schema_version != self.schema_version:
            raise JournalCorruptionError(line_number, "schema_version does not match journal")

    @property
    def lock_path(self) -> Path:
        return self.path.with_suffix(f"{self.path.suffix}.lock")

    def load(self) -> tuple[StoredEvent, ...]:
        if not self.path.is_file():
            return ()
        events: list[StoredEvent] = []
        for line_number, line in enumerate(self.path.read_bytes().splitlines(), start=1):
            if line.strip():
                record = _decode_record(line, line_number)
                for event in record:
                    self._validate_identity(event, line_number)
                    if event.sequence != len(events) + 1:
                        raise JournalCorruptionError(line_number, "sequence is not monotonic")
                    events.append(event)
        return tuple(events)

    def recover_tail(self) -> tuple[StoredEvent, ...]:
        if not self.path.is_file():
            return ()
        data = self.path.read_bytes()
        lines = data.splitlines(keepends=True)
        valid: list[StoredEvent] = []
        offset = 0
        for index, line in enumerate(lines):
            if not line.strip():
                offset += len(line)
                continue
            try:
                record = _decode_record(line.rstrip(b"\r\n"), index + 1)
            except JournalCorruptionError:
                if index != len(lines) - 1 or line.endswith((b"\n", b"\r")):
                    raise
                self.path.write_bytes(data[:offset])
                break
            for event in record:
                self._validate_identity(event, index + 1)
                if event.sequence != len(valid) + 1:
                    raise JournalCorruptionError(index + 1, "sequence is not monotonic")
                valid.append(event)
            offset += len(line)
        return tuple(valid)

    def find_idempotency(self, key: str) -> tuple[StoredEvent, ...]:
        if not key:
            return ()
        matches = tuple(event for event in self.load() if event.idempotency_key == key)
        if not matches:
            return ()
        expected = list(range(matches[0].sequence, matches[0].sequence + len(matches)))
        if [event.sequence for event in matches] != expected:
            raise JournalIdempotencyError(key, "events are not contiguous")
        return matches

    def append(
        self,
        events: tuple[PendingEvent, ...],
        *,
        expected_sequence: int,
        idempotency_key: str | None = None,
    ) -> tuple[StoredEvent, ...]:
        if not events:
            return ()
        if idempotency_key is not None and not idempotency_key.strip():
            raise ValueError("idempotency_key must not be empty")
        with _JOURNAL_LOCK, _file_lock(self.lock_path):
            current = self.load()
            if idempotency_key is not None:
                existing = tuple(event for event in current if event.idempotency_key == idempotency_key)
                if existing:
                    if len(existing) != len(events):
                        raise JournalIdempotencyError(idempotency_key, "event count differs")
                    for stored_event, pending in zip(existing, events, strict=True):
                        if (
                            stored_event.event_type != pending.event_type
                            or dict(stored_event.payload) != dict(pending.payload)
                        ):
                            raise JournalIdempotencyError(idempotency_key, "event payload differs")
                    return existing
            actual = current[-1].sequence if current else 0
            if actual != expected_sequence:
                raise JournalConflictError(expected_sequence, actual)
            stored_events = tuple(
                StoredEvent(
                    event.event_id or f"evt-{uuid.uuid4().hex}",
                    expected_sequence + index + 1,
                    event.event_type,
                    event.payload,
                    idempotency_key,
                    self.mission_id,
                    self.schema_version,
                )
                for index, event in enumerate(events)
            )
            def event_record(event: StoredEvent) -> dict[str, JsonValue]:
                return {
                    "event_id": event.event_id,
                    "sequence": event.sequence,
                    "event_type": event.event_type,
                    "payload": dict(event.payload),
                    **({"idempotency_key": event.idempotency_key} if event.idempotency_key is not None else {}),
                    **({"mission_id": event.mission_id} if event.mission_id is not None else {}),
                    "schema_version": event.schema_version,
                }

            record: dict[str, JsonValue]
            if len(stored_events) == 1:
                record = event_record(stored_events[0])
            else:
                record = {
                    "record_type": "batch",
                    "batch_id": f"batch-{uuid.uuid4().hex}",
                    "events": [event_record(event) for event in stored_events],
                }
            line = json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as stream:
                stream.write(line)
                stream.flush()
                os.fsync(stream.fileno())
            return stored_events


@contextmanager
def _file_lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+") as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
