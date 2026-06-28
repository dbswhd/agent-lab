"""Trading Mission cost telemetry — rounds and token estimates in run.json."""

from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agent_lab.run.meta import patch_run_meta
from agent_lab.trading_mission.topic import mission_id_from_date

_DISCUSS_ROUNDS_RE = re.compile(r"discuss_rounds_used:\s*(\d+)", re.IGNORECASE)
_CHARS_PER_TOKEN = 4


def estimate_tokens_from_chars(chars: int) -> int:
    if chars <= 0:
        return 0
    return max(1, int(round(chars / _CHARS_PER_TOKEN)))


def parse_discuss_rounds_from_plan(plan_md: str) -> int | None:
    match = _DISCUSS_ROUNDS_RE.search(plan_md or "")
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def aggregate_turn_telemetry(run: dict[str, Any]) -> dict[str, Any]:
    """Summarize agent rounds and context payload from run.json turns."""
    turns = [t for t in (run.get("turns") or []) if isinstance(t, dict)]
    latency_ms_total = 0
    payload_chars_total = 0
    payload_chars_max = 0
    agent_parallel_rounds_max = 0
    agents_used: set[str] = set()
    agent_invocations = 0

    for turn in turns:
        agent_parallel_rounds_max = max(
            agent_parallel_rounds_max,
            int(turn.get("agent_parallel_rounds") or 0),
        )
        latency_ms_total += int(turn.get("latency_ms") or 0)
        agents = [str(a) for a in (turn.get("agents") or []) if str(a).strip()]
        agent_invocations += len(agents)
        agents_used.update(agents)
        ctx = turn.get("context") if isinstance(turn.get("context"), dict) else {}
        turn_chars = int(ctx.get("payload_chars_total") or 0)
        payload_chars_total += turn_chars
        summary = ctx.get("summary") if isinstance(ctx.get("summary"), dict) else {}
        turn_max = int(summary.get("payload_chars_max") or turn_chars or 0)
        payload_chars_max = max(payload_chars_max, turn_max)

    return {
        "human_turns": len(turns),
        "agent_parallel_rounds_max": agent_parallel_rounds_max or int(run.get("agent_parallel_rounds") or 0),
        "agent_invocations": agent_invocations,
        "agents": sorted(agents_used),
        "latency_ms_total": latency_ms_total,
        "payload_chars_total": payload_chars_total,
        "payload_chars_max": payload_chars_max,
    }


def build_mission_telemetry(
    session_folder: Path,
    *,
    mission_kind: str,
    wall_ms: float | None = None,
    discuss_skipped: bool = False,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build telemetry payload from session artifacts and run.json."""
    folder = session_folder.expanduser().resolve()
    run_path = folder / "run.json"
    run: dict[str, Any] = {}
    if run_path.is_file():
        try:
            run = json.loads(run_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            run = {}

    plan_path = folder / "plan.md"
    plan_md = ""
    if plan_path.is_file():
        try:
            plan_md = plan_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            plan_md = ""

    discuss_from_plan = parse_discuss_rounds_from_plan(plan_md)
    turn_stats = aggregate_turn_telemetry(run)
    discuss_rounds = discuss_from_plan
    if discuss_rounds is None:
        discuss_rounds = turn_stats["agent_parallel_rounds_max"] if turn_stats["human_turns"] else 0

    from agent_lab.trading_mission.token_budget import turn_budget_telemetry

    budget_stats = turn_budget_telemetry(run)

    input_tokens_est = estimate_tokens_from_chars(turn_stats["payload_chars_total"])
    mock_agents = (os.getenv("AGENT_LAB_MOCK_AGENTS") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )

    payload: dict[str, Any] = {
        "recorded_at": datetime.now(UTC).isoformat(),
        "mission_id": mission_id_from_date(),
        "session_id": folder.name,
        "mission_kind": mission_kind,
        "discuss_skipped": discuss_skipped,
        "discuss_rounds_used": discuss_rounds,
        "mock_agents": mock_agents,
        "tokens_estimated": {
            "input": input_tokens_est,
            "output": 0,
            "method": f"chars/{_CHARS_PER_TOKEN}",
        },
        **turn_stats,
        **budget_stats,
    }
    if wall_ms is not None:
        payload["wall_ms"] = round(wall_ms, 3)
    if extra:
        payload.update(extra)
    return payload


def _token_log_path() -> Path | None:
    pipeline = (os.getenv("QUANT_PIPELINE_ROOT") or "").strip()
    if not pipeline:
        return None
    return Path(pipeline).expanduser().resolve() / "tasks" / ".token_log.jsonl"


def append_token_log_line(telemetry: dict[str, Any]) -> Path | None:
    """Optional rollup into quant-pipeline tasks/.token_log.jsonl."""
    path = _token_log_path()
    if path is None:
        return None
    tokens = telemetry.get("tokens_estimated") if isinstance(telemetry.get("tokens_estimated"), dict) else {}
    record = {
        "ts": telemetry.get("recorded_at") or datetime.now(UTC).isoformat(),
        "task": f"trading_mission:{telemetry.get('mission_kind', 'unknown')}",
        "worker": "agent-lab",
        "session_id": telemetry.get("session_id"),
        "mission_id": telemetry.get("mission_id"),
        "input_tokens_est": tokens.get("input", 0),
        "output_tokens_est": tokens.get("output", 0),
        "discuss_rounds": telemetry.get("discuss_rounds_used", 0),
        "agent_invocations": telemetry.get("agent_invocations", 0),
        "mock_agents": telemetry.get("mock_agents", False),
        "wall_ms": telemetry.get("wall_ms"),
        "budget_pct": telemetry.get("budget_pct"),
        "budget_overflow": telemetry.get("budget_overflow"),
        "agent_calls_used": telemetry.get("agent_calls_used"),
        "agent_calls_cap": telemetry.get("agent_calls_cap"),
        "codex_shell_used": telemetry.get("codex_shell_used"),
        "codex_shell_cap": telemetry.get("codex_shell_cap"),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return path


def record_mission_telemetry(
    session_folder: Path,
    *,
    mission_kind: str,
    wall_ms: float | None = None,
    discuss_skipped: bool = False,
    extra: dict[str, Any] | None = None,
    append_token_log: bool = True,
) -> dict[str, Any]:
    """Persist mission_telemetry on run.json; optionally append token log line."""
    telemetry = build_mission_telemetry(
        session_folder,
        mission_kind=mission_kind,
        wall_ms=wall_ms,
        discuss_skipped=discuss_skipped,
        extra=extra,
    )

    def _patch(run: dict[str, Any]) -> dict[str, Any]:
        history = list(run.get("mission_telemetry_history") or [])
        history.append(telemetry)
        run["mission_telemetry"] = telemetry
        run["mission_telemetry_history"] = history[-20:]
        return run

    patch_run_meta(session_folder, _patch)
    if append_token_log:
        append_token_log_line(telemetry)
    return telemetry
