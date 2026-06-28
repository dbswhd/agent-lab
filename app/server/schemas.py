"""Pydantic request/response models for the Agent Lab API."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from agent_lab.room.messages import MAX_AGENT_PARALLEL_ROUNDS

TURN_PROFILES = frozenset(
    {"quick", "team", "loop", "analyze", "discuss", "review", "free", "specialist", "verified", "divergence", "발산"}
)


class RunRequest(BaseModel):
    topic: str = Field(..., min_length=1, max_length=2000)
    backend: str | None = Field(default=None, description="codex | openai | anthropic")


class RoomRunRequest(BaseModel):
    topic: str = Field(..., min_length=1, max_length=2000)
    agents: list[str] | None = Field(default=None, description="cursor, codex, claude — default: all available")
    synthesize: bool = Field(default=True, description="Scribe plan.md after round")
    session_id: str | None = Field(default=None, description="Continue an existing room session")


class RenameSessionRequest(BaseModel):
    topic: str = Field(..., min_length=1, max_length=200)


class SessionGoalPatchRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000)
    max_checks: int = Field(default=5, ge=1, le=20)


class TaskClaimRequest(BaseModel):
    agent: str = Field(..., min_length=1)


class TeamLeadRequest(BaseModel):
    agent: str = Field(..., min_length=1)


class AgentCapabilitiesPatchRequest(BaseModel):
    capabilities: dict[str, Any] = Field(default_factory=dict)


class TaskCompleteRequest(BaseModel):
    artifact_refs: list[str] = Field(default_factory=list)


class ObjectionResolveRequest(BaseModel):
    verdict: Literal["accepted", "wontfix"]
    note: str = ""


class PlanExecuteDryRunRequest(BaseModel):
    action_index: int = Field(..., ge=1)
    action_kind: str | None = Field(
        default=None,
        description="now | roadmap | legacy, or composite key now:1",
    )
    permissions: dict[str, Any] = Field(default_factory=dict)


class PlanExecuteResolveRequest(BaseModel):
    execution_id: str = Field(..., min_length=1)
    vote: str = Field(..., min_length=1)
    permissions: dict[str, Any] = Field(default_factory=dict)


class PlanExecuteMergeRequest(BaseModel):
    execution_id: str = Field(..., min_length=1)


class PlanExecuteReverifyRequest(BaseModel):
    execution_id: str = Field(..., min_length=1)
    executor: Literal["cursor", "codex"] | None = None
    permissions: dict[str, Any] = Field(default_factory=dict)


class PlanExecuteReviseRequest(BaseModel):
    comment: str = Field(..., min_length=1, max_length=2000)
    chunk_ref: str | None = Field(default=None, max_length=500)
    line_start: int | None = Field(default=None, ge=1)
    line_end: int | None = Field(default=None, ge=1)
    executor: Literal["cursor", "codex"] | None = None
    permissions: dict[str, Any] = Field(default_factory=dict)


class HumanInboxCreateRequest(BaseModel):
    kind: Literal["question", "build"]
    prompt: str = Field(..., min_length=1, max_length=4000)
    source: str | None = Field(default="manual")
    options: list[dict[str, Any]] = Field(default_factory=list)
    multi_select: bool = False
    action_ref: str | None = None
    summary: str | None = None
    risks: list[str] = Field(default_factory=list)
    human_turn_id: int | None = None
    context_ref: str | None = None


class HumanInboxResolveRequest(BaseModel):
    selected: list[str] | None = None
    decision: Literal["go", "defer", "reject"] | None = None
    note: str | None = None
    status: Literal["resolved", "deferred", "rejected"] | None = None
    append_chat: bool = True


class PlanExecuteIsolationOverrideRequest(BaseModel):
    execution_id: str = Field(..., min_length=1)
    mode: str = Field(..., min_length=1)
    confirmation: str = Field(..., min_length=1)
    permissions: dict[str, Any] = Field(default_factory=dict)


class ClarifierAnswersRequest(BaseModel):
    answers: dict[str, str] = Field(default_factory=dict)
    mark_complete: bool = True


class ExternalHandoffRequest(BaseModel):
    stopped_cleanly: bool
    changed_files: list[str] = Field(default_factory=list)
    checks: list[dict[str, Any]] = Field(default_factory=list)
    evidence_summary: str = Field(..., min_length=1)
    risks: list[str] = Field(default_factory=list)
    source: str | None = None
    tool_id: str | None = None


class ContextPreviewRequest(BaseModel):
    session_id: str = Field(..., min_length=1)
    agent: str = Field(..., min_length=1)
    parallel_round: int = Field(default=1, ge=1, le=MAX_AGENT_PARALLEL_ROUNDS)
    review_mode: bool = False
    efficiency_mode: bool = False
    slim_context: bool = False
    permissions: dict[str, Any] = Field(default_factory=dict)
    agents: list[str] | None = None
