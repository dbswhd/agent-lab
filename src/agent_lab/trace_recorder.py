"""OTel-lite local tracer (G5).

Wraps the Room ``on_event`` callback so every agent/tool/dispatch event becomes a
span (duration + token/USD from ``cost_ledger``) appended to ``trace.jsonl`` —
a dependency-free local alternative to Langfuse/LangSmith. The wrapper forwards
every event to the original ``on_event`` unchanged, so SSE behavior is untouched.

Spans are grouped by ``trace_id`` (one per human turn). There is no explicit
turn-end event, so spans are written when they close (``agent_done`` /
``tool_output`` / ``dispatch_done``); any still-open spans are flushed as
``incomplete`` on ``turn_failed`` / ``run_cancelled``. Tracing must never break a
turn — every handler is wrapped so failures are swallowed.
"""

from __future__ import annotations

from agent_lab.time_utils import utc_now_iso
from agent_lab.env_flags import env_bool
from agent_lab.run.state import RunStateLike
from agent_lab.trace_episode import episode_fields
import json
import time
from pathlib import Path
from typing import Any, Callable

OnEvent = Callable[[str, dict[str, Any]], None]


def trace_enabled() -> bool:
    return env_bool("AGENT_LAB_TRACE", default=True)


def _now() -> tuple[float, str]:
    return time.monotonic(), utc_now_iso()


class TraceRecorder:
    """Callable that records spans and forwards to an inner ``on_event``."""

    def __init__(
        self,
        folder: Path | None,
        run_meta: RunStateLike | None,
        inner: OnEvent | None,
        *,
        human_turn: int = 0,
    ) -> None:
        self._folder = folder
        self._run_meta = run_meta
        self._inner = inner
        self._trace_id = f"t{human_turn}"
        self._human_turn = human_turn
        self._path = (folder / "trace.jsonl") if folder is not None else None
        self._n = 0
        self._agents: dict[tuple[str, Any], dict[str, Any]] = {}
        self._tools: dict[tuple[str, Any], dict[str, Any]] = {}
        self._dispatch: list[dict[str, Any]] = []

    # -- event entry ----------------------------------------------------
    def __call__(self, typ: str, payload: dict[str, Any]) -> None:
        try:
            self._handle(typ, payload if isinstance(payload, dict) else {})
        except Exception:
            pass
        if self._inner is not None:
            self._inner(typ, payload)

    # -- helpers --------------------------------------------------------
    def _next_id(self) -> str:
        self._n += 1
        return f"s{self._n}"

    def _agent_cost(self, agent: str) -> tuple[int, int, float]:
        led = (self._run_meta or {}).get("cost_ledger") or {}
        entry = (led.get("by_agent") or {}).get(agent) or {}
        return (
            int(entry.get("tokens_in", 0) or 0),
            int(entry.get("tokens_out", 0) or 0),
            float(entry.get("usd", 0.0) or 0.0),
        )

    def _write(self, span: dict[str, Any]) -> None:
        if self._path is None:
            return
        try:
            span.update(episode_fields(self._folder, self._human_turn))
            with self._path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(span, ensure_ascii=False) + "\n")
        except Exception:
            pass

    def _close(self, span: dict[str, Any], status: str) -> None:
        mono, wall = _now()
        span["end"] = wall
        span["dur_ms"] = round((mono - span.pop("_mono", mono)) * 1000.0, 1)
        span["status"] = status
        self._write(span)

    # -- handlers -------------------------------------------------------
    def _handle(self, typ: str, payload: dict[str, Any]) -> None:
        agent = str(payload.get("agent") or "")
        rnd = payload.get("round")
        if typ == "agent_start":
            self._open_agent(agent, rnd)
        elif typ in ("agent_done", "agent_error"):
            self._close_agent(agent, rnd, "ok" if typ == "agent_done" else "error")
        elif typ == "tool_start":
            self._open_tool(agent, rnd, str(payload.get("tool") or "tool"))
        elif typ == "tool_output":
            self._close_tool(agent, rnd)
        elif typ == "dispatch_start":
            self._open_dispatch(payload)
        elif typ in ("dispatch_done",):
            self._close_dispatch()
        elif typ in ("turn_failed", "run_cancelled"):
            self._flush_open()

    def _open_agent(self, agent: str, rnd: Any) -> None:
        mono, wall = _now()
        parent = self._dispatch[-1]["span_id"] if self._dispatch else None
        ti, to, usd = self._agent_cost(agent)
        self._agents[(agent, rnd)] = {
            "trace_id": self._trace_id,
            "span_id": self._next_id(),
            "parent_id": parent,
            "kind": "agent",
            "name": agent,
            "round": rnd,
            "start": wall,
            "_mono": mono,
            "_cost0": (ti, to, usd),
        }

    def _close_agent(self, agent: str, rnd: Any, status: str) -> None:
        span = self._agents.pop((agent, rnd), None)
        if span is None:
            return
        ti0, to0, usd0 = span.pop("_cost0", (0, 0, 0.0))
        ti, to, usd = self._agent_cost(agent)
        span["tokens_in"] = max(0, ti - ti0)
        span["tokens_out"] = max(0, to - to0)
        span["usd"] = round(max(0.0, usd - usd0), 6)
        self._close(span, status)

    def _open_tool(self, agent: str, rnd: Any, tool: str) -> None:
        mono, wall = _now()
        parent_span = self._agents.get((agent, rnd))
        self._tools[(agent, rnd)] = {
            "trace_id": self._trace_id,
            "span_id": self._next_id(),
            "parent_id": parent_span["span_id"] if parent_span else None,
            "kind": "tool",
            "name": tool,
            "round": rnd,
            "start": wall,
            "_mono": mono,
        }

    def _close_tool(self, agent: str, rnd: Any) -> None:
        span = self._tools.pop((agent, rnd), None)
        if span is not None:
            self._close(span, "ok")

    def _open_dispatch(self, payload: dict[str, Any]) -> None:
        mono, wall = _now()
        self._dispatch.append(
            {
                "trace_id": self._trace_id,
                "span_id": self._next_id(),
                "parent_id": None,
                "kind": "dispatch",
                "name": str(payload.get("op") or payload.get("dispatch_id") or "dispatch"),
                "start": wall,
                "_mono": mono,
            }
        )

    def _close_dispatch(self) -> None:
        if self._dispatch:
            self._close(self._dispatch.pop(), "ok")

    def _flush_open(self) -> None:
        for bucket in (self._tools, self._agents):
            for span in list(bucket.values()):
                self._close(span, "incomplete")
            bucket.clear()
        while self._dispatch:
            self._close(self._dispatch.pop(), "incomplete")


def install_tracer(
    folder: Path | None,
    run_meta: RunStateLike | None,
    on_event: OnEvent | None,
    *,
    human_turn: int = 0,
) -> OnEvent | None:
    """Return ``on_event`` wrapped in a TraceRecorder, or unchanged if disabled."""
    if not trace_enabled():
        return on_event
    return TraceRecorder(folder, run_meta, on_event, human_turn=human_turn)


def record_tool_span(
    folder: Path | None,
    *,
    name: str,
    dur_ms: float | None,
    status: str,
    data: dict[str, Any] | None = None,
) -> None:
    """Append a standalone ``kind:"tool"`` span to ``trace.jsonl`` (G7).

    For tools agent-lab executes out-of-band (slash commands, external tools)
    that don't flow through the Room event stream / ``TraceRecorder``. Never
    raises — tracing must not break a tool call.
    """
    _append_standalone_span(
        folder,
        kind="tool",
        name=name,
        dur_ms=dur_ms,
        status=status,
        data=data,
        trace_id="tools",
    )


def record_agent_span(
    folder: Path | None,
    *,
    name: str,
    agent_id: str,
    dur_ms: float | None,
    status: str,
    tokens_in: int = 0,
    tokens_out: int = 0,
    usd: float = 0.0,
    data: dict[str, Any] | None = None,
) -> None:
    """Append a standalone ``kind:"agent"`` span for oracle/scribe/execute sidecars."""
    payload = {"agent": agent_id, **(data or {})}
    _append_standalone_span(
        folder,
        kind="agent",
        name=name,
        dur_ms=dur_ms,
        status=status,
        data=payload,
        trace_id="sidecar",
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        usd=usd,
    )


def record_control_span(
    folder: Path | None,
    *,
    name: str,
    status: str,
    human_turn: int | None = None,
    data: dict[str, str | int | float | bool | None] | None = None,
) -> None:
    _append_standalone_span(
        folder,
        kind="control",
        name=name,
        dur_ms=0.0,
        status=status,
        data=data,
        trace_id="control",
        human_turn=human_turn,
    )


def _append_standalone_span(
    folder: Path | None,
    *,
    kind: str,
    name: str,
    dur_ms: float | None,
    status: str,
    trace_id: str,
    data: dict[str, Any] | None = None,
    tokens_in: int = 0,
    tokens_out: int = 0,
    usd: float = 0.0,
    human_turn: int | None = None,
) -> None:
    if not trace_enabled() or folder is None:
        return
    try:
        import uuid

        _, wall = _now()
        span: dict[str, Any] = {
            "trace_id": trace_id,
            "span_id": f"x{uuid.uuid4().hex[:8]}",
            "parent_id": None,
            "kind": kind,
            "name": name,
            "end": wall,
            "dur_ms": round(dur_ms, 1) if dur_ms is not None else None,
            "status": status,
        }
        span.update(episode_fields(folder, human_turn))
        if tokens_in or tokens_out:
            span["tokens_in"] = tokens_in
            span["tokens_out"] = tokens_out
        if usd:
            span["usd"] = round(usd, 6)
        if data:
            span["data"] = data
        with (folder / "trace.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(span, ensure_ascii=False) + "\n")
    except Exception:
        pass
