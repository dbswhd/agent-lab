from __future__ import annotations

import json
import os
from contextlib import contextmanager
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from collections.abc import Iterator
from typing import Any

import fcntl

from agent_lab.mission.lease import ActivityLease, ActivityLeaseStore, LeaseConflictError
from agent_lab.mission.recovery import RecoveryAction, RecoveryDecision, SideEffectState, decide_recovery


class QueueConflictError(Exception):
    pass


class QueueCorruptionError(ValueError):
    pass


class QueueState(StrEnum):
    QUEUED = "queued"
    CLAIMED = "claimed"
    COMPLETED = "completed"
    NEEDS_RECONCILE = "needs_reconcile"


@dataclass(frozen=True, slots=True)
class QueuedActivity:
    activity_id: str
    mission_id: str
    kind: str
    priority: int
    idempotency_key: str
    state: QueueState = QueueState.QUEUED
    side_effect_state: SideEffectState = SideEffectState.NOT_STARTED
    owner_id: str | None = None
    lease_token: str | None = None


@dataclass(frozen=True, slots=True)
class ClaimedActivity:
    activity: QueuedActivity
    lease: ActivityLease


def _decode(activity_id: str, raw: Any) -> QueuedActivity:
    if not isinstance(raw, dict):
        raise QueueCorruptionError(f"activity {activity_id} must be an object")
    mission_id = raw.get("mission_id")
    kind = raw.get("kind")
    priority = raw.get("priority")
    idempotency_key = raw.get("idempotency_key")
    if (
        not isinstance(mission_id, str)
        or not isinstance(kind, str)
        or not isinstance(priority, int)
        or isinstance(priority, bool)
        or not isinstance(idempotency_key, str)
    ):
        raise QueueCorruptionError(f"activity {activity_id} identity is invalid")
    try:
        state = QueueState(raw.get("state", QueueState.QUEUED))
        side_effect_state = SideEffectState(raw.get("side_effect_state", SideEffectState.NOT_STARTED))
    except ValueError as exc:
        raise QueueCorruptionError(f"activity {activity_id} state is invalid") from exc
    owner_id = raw.get("owner_id")
    lease_token = raw.get("lease_token")
    if owner_id is not None and not isinstance(owner_id, str):
        raise QueueCorruptionError(f"activity {activity_id} owner is invalid")
    if lease_token is not None and not isinstance(lease_token, str):
        raise QueueCorruptionError(f"activity {activity_id} lease token is invalid")
    return QueuedActivity(
        activity_id,
        mission_id,
        kind,
        priority,
        idempotency_key,
        state,
        side_effect_state,
        owner_id,
        lease_token,
    )


def _encode(activity: QueuedActivity) -> dict[str, str | int | None]:
    return {
        "mission_id": activity.mission_id,
        "kind": activity.kind,
        "priority": activity.priority,
        "idempotency_key": activity.idempotency_key,
        "state": activity.state.value,
        "side_effect_state": activity.side_effect_state.value,
        "owner_id": activity.owner_id,
        "lease_token": activity.lease_token,
    }


@dataclass(frozen=True, slots=True)
class ActivityQueue:
    path: Path
    leases: ActivityLeaseStore

    @classmethod
    def for_session(cls, session_folder: Path) -> ActivityQueue:
        root = session_folder / ".agent-lab"
        return cls(root / "activities.json", ActivityLeaseStore(root / "activity-leases.json"))

    @property
    def lock_path(self) -> Path:
        return self.path.with_suffix(f"{self.path.suffix}.lock")

    def enqueue(self, activity: QueuedActivity) -> QueuedActivity:
        with _file_lock(self.lock_path):
            records = self._read()
            existing = records.get(activity.activity_id)
            if existing is not None:
                if existing.idempotency_key != activity.idempotency_key:
                    raise QueueConflictError(f"activity id reused: {activity.activity_id}")
                return existing
            duplicate = next((item for item in records.values() if item.idempotency_key == activity.idempotency_key), None)
            if duplicate is not None:
                return duplicate
            records[activity.activity_id] = activity
            self._write(records)
            return activity

    def claim_next(self, owner_id: str, *, now: float, ttl_s: float) -> ClaimedActivity | None:
        with _file_lock(self.lock_path):
            records = self._read()
            candidates = [item for item in records.values() if item.state is QueueState.QUEUED]
            if not candidates:
                return None
            candidate = min(candidates, key=lambda item: (-item.priority, item.activity_id))
            lease = self.leases.claim(candidate.activity_id, candidate.mission_id, owner_id, now=now, ttl_s=ttl_s)
            claimed = QueuedActivity(
                candidate.activity_id,
                candidate.mission_id,
                candidate.kind,
                candidate.priority,
                candidate.idempotency_key,
                QueueState.CLAIMED,
                candidate.side_effect_state,
                owner_id,
                lease.token,
            )
            records[candidate.activity_id] = claimed
            self._write(records)
            return ClaimedActivity(claimed, lease)

    def heartbeat(self, activity_id: str, owner_id: str, token: str, *, now: float, ttl_s: float) -> ActivityLease:
        with _file_lock(self.lock_path):
            activity = self._require_claim(self._read(), activity_id, owner_id, token)
            lease = self.leases.heartbeat(activity_id, owner_id, token, now=now, ttl_s=ttl_s)
            if activity.state is not QueueState.CLAIMED:
                raise QueueConflictError(f"activity is not claimed: {activity_id}")
            return lease

    def record_side_effect(
        self,
        activity_id: str,
        owner_id: str,
        token: str,
        state: SideEffectState,
    ) -> QueuedActivity:
        with _file_lock(self.lock_path):
            records = self._read()
            activity = self._require_claim(records, activity_id, owner_id, token)
            updated = QueuedActivity(
                activity.activity_id,
                activity.mission_id,
                activity.kind,
                activity.priority,
                activity.idempotency_key,
                activity.state,
                state,
                activity.owner_id,
                activity.lease_token,
            )
            records[activity_id] = updated
            self._write(records)
            return updated

    def complete(self, activity_id: str, owner_id: str, token: str, *, now: float) -> QueuedActivity:
        with _file_lock(self.lock_path):
            records = self._read()
            activity = self._require_claim(records, activity_id, owner_id, token)
            completed = QueuedActivity(
                activity.activity_id,
                activity.mission_id,
                activity.kind,
                activity.priority,
                activity.idempotency_key,
                QueueState.COMPLETED,
                SideEffectState.COMMITTED,
            )
            records[activity_id] = completed
            self._write(records)
            self.leases.release(activity_id, owner_id, token, now=now)
            return completed

    def recover(self, *, now: float) -> tuple[RecoveryDecision, ...]:
        expired = tuple(lease for lease in self.leases.snapshot() if lease.is_expired(now))
        if not expired:
            return ()
        with _file_lock(self.lock_path):
            records = self._read()
            decisions: list[RecoveryDecision] = []
            changed = False
            for lease in expired:
                activity = records.get(lease.activity_id)
                if activity is None or activity.state is not QueueState.CLAIMED:
                    continue
                decision = decide_recovery(activity.activity_id, activity.side_effect_state)
                decisions.append(decision)
                state = QueueState.NEEDS_RECONCILE if decision.action is RecoveryAction.RECONCILE else (
                    QueueState.COMPLETED if decision.action is RecoveryAction.COMPLETE else QueueState.QUEUED
                )
                records[activity.activity_id] = QueuedActivity(
                    activity.activity_id,
                    activity.mission_id,
                    activity.kind,
                    activity.priority,
                    activity.idempotency_key,
                    state,
                    activity.side_effect_state,
                )
                changed = True
            if changed:
                self._write(records)
            for lease in expired:
                self._release_expired_lease(lease, now)
            return tuple(decisions)

    def _release_expired_lease(self, lease: ActivityLease, now: float) -> None:
        try:
            self.leases.release(lease.activity_id, lease.owner_id, lease.token, now=now)
        except LeaseConflictError:
            return

    def snapshot(self) -> tuple[QueuedActivity, ...]:
        with _file_lock(self.lock_path):
            return tuple(self._read().values())

    def _require_claim(
        self,
        records: dict[str, QueuedActivity],
        activity_id: str,
        owner_id: str,
        token: str,
    ) -> QueuedActivity:
        activity = records.get(activity_id)
        if (
            activity is None
            or activity.state is not QueueState.CLAIMED
            or activity.owner_id != owner_id
            or activity.lease_token != token
        ):
            raise QueueConflictError(f"activity claim mismatch: {activity_id}")
        return activity

    def _read(self) -> dict[str, QueuedActivity]:
        if not self.path.is_file():
            return {}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise QueueCorruptionError(str(exc)) from exc
        if not isinstance(raw, dict):
            raise QueueCorruptionError("activity queue must be an object")
        return {activity_id: _decode(activity_id, value) for activity_id, value in raw.items()}

    def _write(self, records: dict[str, QueuedActivity]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(f"{self.path.suffix}.tmp")
        payload = {activity_id: _encode(activity) for activity_id, activity in records.items()}
        temp.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        with temp.open("rb") as stream:
            os.fsync(stream.fileno())
        temp.replace(self.path)


@contextmanager
def _file_lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+") as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
