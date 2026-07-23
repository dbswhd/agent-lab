"""Typed input boundary for dogfood readiness evidence."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator


class EvidenceTier(StrEnum):
    MOCK = "mock"
    BROWSER = "browser"
    LIVE = "live"


class GateStatus(StrEnum):
    PASS = "PASS"
    OPEN = "OPEN"
    DEFERRED = "deferred"


class SessionKind(StrEnum):
    SUCCESS = "success"
    REPAIR = "repair"


class TimeWindow(BaseModel):
    model_config = ConfigDict(frozen=True)
    started_at: datetime
    ended_at: datetime


class EvidenceRecord(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: str
    tier: EvidenceTier
    status: GateStatus
    sample_size: int = Field(ge=0)
    raw_paths: tuple[Path, ...] = ()
    owner: str | None = None
    next_gate: str | None = None

    @model_validator(mode="after")
    def require_proof_or_next_gate(self) -> EvidenceRecord:
        if self.status is GateStatus.PASS and not self.raw_paths:
            raise ValueError("PASS evidence requires at least one raw path")
        if self.status is not GateStatus.PASS and (not self.owner or not self.next_gate):
            raise ValueError("OPEN/deferred evidence requires owner and next_gate")
        return self


class SessionRecord(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: str
    tier: EvidenceTier
    kind: SessionKind
    run_path: Path


class GateEvent(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: str
    opened_at: datetime
    closed_at: datetime


class ParityArm(BaseModel):
    model_config = ConfigDict(frozen=True)
    sample_size: int = Field(ge=0)
    successes: int = Field(ge=0)

    @model_validator(mode="after")
    def successes_fit_sample(self) -> ParityArm:
        if self.successes > self.sample_size:
            raise ValueError("parity successes cannot exceed sample_size")
        return self


class ParityComparison(BaseModel):
    model_config = ConfigDict(frozen=True)
    cohort: ParityArm
    noncohort: ParityArm


class OperationalGate(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: str
    status: GateStatus
    owner: str
    next_gate: str
    raw_paths: tuple[Path, ...] = ()

    @model_validator(mode="after")
    def pass_requires_proof(self) -> OperationalGate:
        if self.status is GateStatus.PASS and not self.raw_paths:
            raise ValueError("PASS operational gate requires at least one raw path")
        return self


class Thresholds(BaseModel):
    model_config = ConfigDict(frozen=True)
    oracle_coverage_min: float = Field(ge=0, le=1)
    false_success_max: int = Field(ge=0)
    retry_cap: int = Field(ge=1)
    parity_gap_max: float = Field(ge=0, le=1)


class ReadinessManifest(BaseModel):
    model_config = ConfigDict(frozen=True)
    schema_version: int
    owner: str
    commit_sha: str = Field(min_length=7)
    window: TimeWindow
    flags: dict[str, str]
    cohort_ids: tuple[str, ...]
    evidence: tuple[EvidenceRecord, ...]
    sessions: tuple[SessionRecord, ...]
    gate_events: tuple[GateEvent, ...]
    parity: ParityComparison
    operational_gates: tuple[OperationalGate, ...]
    thresholds: Thresholds


class OracleResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    verdict: str = ""
    evidence: tuple[str, ...] = ()
    checked_paths: tuple[str, ...] = ()


class RepairAttempt(BaseModel):
    model_config = ConfigDict(frozen=True)
    attempt: int = 0
    oracle_before: OracleResult | None = None
    oracle_after: OracleResult | None = None


class Execution(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: str
    status: str = ""
    oracle: OracleResult | None = None
    verify_retries: int = 0
    repair_history: tuple[RepairAttempt, ...] = ()


class RunArtifact(BaseModel):
    model_config = ConfigDict(frozen=True)
    executions: tuple[Execution, ...] = ()


def resolve_artifact(path: Path, base: Path) -> Path:
    return path if path.is_absolute() else base / path


def load_manifest(path: Path) -> ReadinessManifest:
    """Parse a manifest and fail closed on missing raw artifacts."""
    manifest = ReadinessManifest.model_validate_json(path.read_text(encoding="utf-8"))
    raw_paths = [
        *[raw for row in manifest.evidence for raw in row.raw_paths],
        *[row.run_path for row in manifest.sessions],
        *[raw for row in manifest.operational_gates for raw in row.raw_paths],
    ]
    missing = [str(raw) for raw in raw_paths if not resolve_artifact(raw, Path.cwd()).is_file()]
    if missing:
        raise ValueError(f"raw artifact path missing: {', '.join(missing)}")
    return manifest
