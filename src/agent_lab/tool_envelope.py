"""Unified tool descriptor + result envelope (G7).

agent-lab's directly-executed tools live in three fragmented systems — slash
commands (``command_registry``), external subprocess tools (``external_tools`` /
``runtime.external_runner``), and server handlers — each returning a different
result shape. This module gives them ONE typed descriptor (a view over the
existing catalog rows) and ONE normalized result envelope, so anything consuming
a tool result stops re-deriving kind-specific branches when a tool is added.

This does NOT touch the agent bridges: Claude/Codex/Cursor run their own tools
internally; only the tools agent-lab executes itself flow through here.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

ToolKind = Literal["client", "server", "external", "agent_invoke", "plugin"]


@dataclass(frozen=True)
class ToolDescriptor:
    """Typed view of a ``list_commands`` catalog row."""

    id: str
    slash: str | None
    label: str | None
    description: str | None
    scope: str | None
    kind: str | None
    agent: str | None
    enabled: bool
    disabled_reason: str | None
    requires_human_confirm: bool
    source: str | None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> ToolDescriptor:
        return cls(
            id=str(row.get("id") or ""),
            slash=row.get("slash"),
            label=row.get("label"),
            description=row.get("description"),
            scope=row.get("scope"),
            kind=row.get("kind"),
            agent=row.get("agent"),
            enabled=row.get("enabled") is not False,
            disabled_reason=row.get("disabled_reason"),
            requires_human_confirm=bool(row.get("requires_human_confirm")),
            source=row.get("source"),
        )

    def gate(self) -> tuple[bool, str | None]:
        """Unified allowlist view: ``(enabled, disabled_reason)``."""
        return self.enabled, (None if self.enabled else self.disabled_reason)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "slash": self.slash,
            "label": self.label,
            "description": self.description,
            "scope": self.scope,
            "kind": self.kind,
            "agent": self.agent,
            "enabled": self.enabled,
            "disabled_reason": self.disabled_reason,
            "requires_human_confirm": self.requires_human_confirm,
            "source": self.source,
        }


@dataclass
class ToolResult:
    """Normalized envelope for a directly-executed tool."""

    ok: bool
    tool_id: str
    kind: str | None
    status: str | None
    content: str | None = None
    error: str | None = None
    data: dict[str, Any] = field(default_factory=dict)
    duration_ms: float | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        # ``raw`` is intentionally omitted — it's the un-normalized source.
        return {
            "ok": self.ok,
            "tool_id": self.tool_id,
            "kind": self.kind,
            "status": self.status,
            "content": self.content,
            "error": self.error,
            "data": self.data,
            "duration_ms": self.duration_ms,
        }


def _first_str(*vals: Any) -> str | None:
    for v in vals:
        if isinstance(v, str) and v.strip():
            return v
    return None


def normalize_tool_result(
    raw: dict[str, Any],
    *,
    descriptor: ToolDescriptor | None = None,
    duration_ms: float | None = None,
) -> ToolResult:
    """Map an ``execute_command`` return dict into a :class:`ToolResult`.

    Pure function (no I/O). Handles every kind the dispatcher emits plus the
    error/unknown shape.
    """
    raw = raw if isinstance(raw, dict) else {}
    ok = bool(raw.get("ok"))
    kind = raw.get("kind") or (descriptor.kind if descriptor else None)
    tool_id = (descriptor.id if descriptor else None) or str(
        (raw.get("command") or {}).get("id") or ""
    )

    def _build(*, status: str | None, content: str | None, error: str | None, data: dict[str, Any]) -> ToolResult:
        return ToolResult(
            ok=ok,
            tool_id=tool_id,
            kind=kind,
            status=status,
            content=content,
            error=error,
            data=data,
            duration_ms=duration_ms,
            raw=raw,
        )

    if not ok and not isinstance(raw.get("result"), dict):
        # Gate failure (unknown/disabled command, unsupported kind): the error is
        # at the top level, with no tool-execution ``result`` payload.
        return _build(status="error", content=None, error=raw.get("detail"), data={})

    if kind == "client":
        return _build(status="client_dispatch", content=raw.get("handler"), error=None, data={"handler": raw.get("handler")})

    if kind == "server":
        result = raw.get("result") if isinstance(raw.get("result"), dict) else {}
        content = _first_str(result.get("detail"), result.get("verdict"), result.get("summary"))
        return _build(status="ok", content=content, error=None, data=result)

    if kind == "external":
        result = raw.get("result") if isinstance(raw.get("result"), dict) else {}
        status = result.get("status") or ("ok" if ok else "error")
        content = _first_str(result.get("stdout"), result.get("detail"))
        error = None if ok else _first_str(result.get("stderr"), result.get("detail"))
        return _build(status=status, content=content, error=error, data=result)

    if kind == "agent_invoke":
        return _build(status="ok", content=raw.get("text"), error=None, data={"agent": raw.get("agent")})

    if kind == "plugin":
        return _build(status="ok", content=raw.get("detail"), error=None, data={})

    # Unknown kind.
    return _build(status="error", content=None, error=raw.get("detail") or f"unsupported kind: {kind}", data={})


def tool_descriptors(catalog: dict[str, Any]) -> list[ToolDescriptor]:
    """Typed view over ``list_commands(...)['commands']``."""
    return [ToolDescriptor.from_row(row) for row in (catalog.get("commands") or []) if isinstance(row, dict)]
