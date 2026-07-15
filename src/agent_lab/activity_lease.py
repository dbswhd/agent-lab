from __future__ import annotations

import json
import os
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Iterator
from typing import Any

import fcntl


class LeaseConflictError(Exception):
    def __init__(self, activity_id: str, owner_id: str) -> None:
        self.activity_id = activity_id
        self.owner_id = owner_id
        super().__init__(activity_id, owner_id)

    def __str__(self) -> str:
        return f"activity lease is owned by {self.owner_id}: {self.activity_id}"


class LeaseStoreCorruptionError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ActivityLease:
    activity_id: str
    mission_id: str
    owner_id: str
    token: str
    acquired_at: float
    heartbeat_at: float
    expires_at: float

    def is_expired(self, now: float) -> bool:
        return self.expires_at <= now


def _positive_ttl(ttl_s: float) -> None:
    if ttl_s <= 0:
        raise ValueError("lease ttl must be positive")


def _decode(activity_id: str, raw: Any) -> ActivityLease:
    if not isinstance(raw, dict):
        raise LeaseStoreCorruptionError(f"lease {activity_id} must be an object")
    mission_id = raw.get("mission_id")
    owner_id = raw.get("owner_id")
    token = raw.get("token")
    if (
        not isinstance(mission_id, str)
        or not mission_id
        or not isinstance(owner_id, str)
        or not owner_id
        or not isinstance(token, str)
        or not token
    ):
        raise LeaseStoreCorruptionError(f"lease {activity_id} identity is invalid")
    acquired_at = raw.get("acquired_at")
    heartbeat_at = raw.get("heartbeat_at")
    expires_at = raw.get("expires_at")
    if (
        not isinstance(acquired_at, (int, float))
        or isinstance(acquired_at, bool)
        or not isinstance(heartbeat_at, (int, float))
        or isinstance(heartbeat_at, bool)
        or not isinstance(expires_at, (int, float))
        or isinstance(expires_at, bool)
    ):
        raise LeaseStoreCorruptionError(f"lease {activity_id} timestamps are invalid")
    return ActivityLease(
        activity_id=activity_id,
        mission_id=mission_id,
        owner_id=owner_id,
        token=token,
        acquired_at=float(acquired_at),
        heartbeat_at=float(heartbeat_at),
        expires_at=float(expires_at),
    )


def _encode(lease: ActivityLease) -> dict[str, str | float]:
    return {
        "mission_id": lease.mission_id,
        "owner_id": lease.owner_id,
        "token": lease.token,
        "acquired_at": lease.acquired_at,
        "heartbeat_at": lease.heartbeat_at,
        "expires_at": lease.expires_at,
    }


@dataclass(frozen=True, slots=True)
class ActivityLeaseStore:
    path: Path

    @property
    def lock_path(self) -> Path:
        return self.path.with_suffix(f"{self.path.suffix}.lock")

    def snapshot(self) -> tuple[ActivityLease, ...]:
        with _file_lock(self.lock_path):
            return tuple(self._read().values())

    def claim(self, activity_id: str, mission_id: str, owner_id: str, *, now: float, ttl_s: float) -> ActivityLease:
        _positive_ttl(ttl_s)
        with _file_lock(self.lock_path):
            leases = self._read()
            current = leases.get(activity_id)
            if current is not None and not current.is_expired(now) and current.owner_id != owner_id:
                raise LeaseConflictError(activity_id, current.owner_id)
            token = current.token if current is not None and current.owner_id == owner_id else uuid.uuid4().hex
            lease = ActivityLease(activity_id, mission_id, owner_id, token, now, now, now + ttl_s)
            leases[activity_id] = lease
            self._write(leases)
            return lease

    def heartbeat(
        self,
        activity_id: str,
        owner_id: str,
        token: str,
        *,
        now: float,
        ttl_s: float,
    ) -> ActivityLease:
        _positive_ttl(ttl_s)
        with _file_lock(self.lock_path):
            leases = self._read()
            current = self._require_owner(leases, activity_id, owner_id, token, now)
            lease = ActivityLease(
                current.activity_id,
                current.mission_id,
                current.owner_id,
                current.token,
                current.acquired_at,
                now,
                now + ttl_s,
            )
            leases[activity_id] = lease
            self._write(leases)
            return lease

    def release(self, activity_id: str, owner_id: str, token: str, *, now: float) -> None:
        with _file_lock(self.lock_path):
            leases = self._read()
            self._require_owner(leases, activity_id, owner_id, token, now, allow_expired=True)
            del leases[activity_id]
            self._write(leases)

    def recover_expired(self, *, now: float) -> tuple[ActivityLease, ...]:
        with _file_lock(self.lock_path):
            leases = self._read()
            expired = tuple(lease for lease in leases.values() if lease.is_expired(now))
            if expired:
                for lease in expired:
                    del leases[lease.activity_id]
                self._write(leases)
            return expired

    def _require_owner(
        self,
        leases: dict[str, ActivityLease],
        activity_id: str,
        owner_id: str,
        token: str,
        now: float,
        *,
        allow_expired: bool = False,
    ) -> ActivityLease:
        current = leases.get(activity_id)
        if current is None or current.owner_id != owner_id or current.token != token:
            raise LeaseConflictError(activity_id, owner_id)
        if not allow_expired and current.is_expired(now):
            raise LeaseConflictError(activity_id, "expired")
        return current

    def _read(self) -> dict[str, ActivityLease]:
        if not self.path.is_file():
            return {}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise LeaseStoreCorruptionError(str(exc)) from exc
        if not isinstance(raw, dict):
            raise LeaseStoreCorruptionError("lease store must be an object")
        return {activity_id: _decode(activity_id, value) for activity_id, value in raw.items()}

    def _write(self, leases: dict[str, ActivityLease]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(f"{self.path.suffix}.tmp")
        payload = {activity_id: _encode(lease) for activity_id, lease in leases.items()}
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
