#!/usr/bin/env python3
"""Run one AGENT_LAB_PIPELINE mission (live or mock Room + mission_loop advance)."""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


@dataclass
class MissionSpec:
    name: str
    topic: str
    goal_text: str
    agents: list[str] | None = None

    def __post_init__(self) -> None:
        if self.agents is None:
            self.agents = ["cursor", "codex", "claude"]


def _utc_slug() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def _install_consensus_mock() -> None:
    import json as _json

    from agent_lab.agents.registry import AgentReply

    per_agent: dict[str, int] = {}

    def patched(agent, system, user, **kwargs):
        if kwargs.get("scribe"):
            return AgentReply(text="## Plan\n\n- mock\n")
        n = per_agent.get(agent, 0) + 1
        per_agent[agent] = n

        def envelope(act: str, body: str) -> AgentReply:
            payload = _json.dumps({"act": act, "refs": [], "confidence": 0.9})
            return AgentReply(text=f"```agent-envelope\n{payload}\n```\n{body}")

        if agent == "cursor" and n == 1:
            return envelope("PROPOSE", "Proceed with the anchored plan in the goal.")
        return envelope("ENDORSE", "Agreed.")

    import agent_lab.agents.registry as registry

    registry.call_agent_reply = patched  # type: ignore[method-assign]
    registry.call_agent = lambda agent, system, user, **kw: patched(agent, system, user, **kw).text


def run_mission(
    spec: MissionSpec,
    *,
    sessions_root: Path,
    session_id: str | None = None,
    live: bool = True,
) -> dict[str, Any]:
    os.environ["AGENT_LAB_PIPELINE"] = "1"
    os.environ["AGENT_LAB_MISSION_LOOP"] = "1"
    os.environ["AGENT_LAB_MOCK_AGENTS"] = "0" if live else "1"
    if not live:
        _install_consensus_mock()

    from agent_lab import room
    from agent_lab.clarity import clarity_threshold_met, score_ambiguity
    from agent_lab.consensus_gate import consensus_gate_met
    from agent_lab.mission.advance import maybe_advance_mission
    from agent_lab.mission.loop import enable_mission_loop, get_mission_loop, pipeline_enabled
    from agent_lab.run.meta import patch_run_meta, read_run_meta
    from agent_lab.verified_loop import approve_verified_loop, init_verified_loop, record_proposed_goal

    sid = session_id or f"pipeline-mission-{spec.name}-{_utc_slug()}"
    folder = sessions_root / sid
    folder.mkdir(parents=True, exist_ok=True)

    result: dict[str, Any] = {
        "name": spec.name,
        "session_id": sid,
        "live": live,
        "checks": [],
    }

    def record(name: str, ok: bool, detail: str) -> None:
        result["checks"].append({"name": name, "ok": ok, "detail": detail})

    record("pipeline_flag", pipeline_enabled(), "AGENT_LAB_PIPELINE=1")

    folder, _messages, _plan = room.run_room(
        spec.topic,
        agents=spec.agents,
        synthesize=False,
        sessions_base=sessions_root,
        session_folder=folder,
        consensus_mode=True,
        efficiency_mode=live,
    )
    run = read_run_meta(folder)
    turn_c = ((run.get("turns") or [{}])[0].get("consensus") or {}) if run.get("turns") else {}
    run_c = run.get("consensus") or {}
    record("room_consensus_turn", turn_c.get("status") == "reached", f"turn={turn_c.get('status')!r}")
    record("room_consensus_run", run_c.get("status") == "reached", f"run.consensus={run_c.get('status')!r}")
    record("consensus_gate", consensus_gate_met(run), "consensus_gate_met")

    init_verified_loop(folder)
    record_proposed_goal(
        folder,
        {
            "goal": spec.goal_text,
            "completion_promise": "MISSION_DONE",
            "criteria": "plan gate + verify pass",
        },
        source="pipeline_mission",
    )

    def _pending(run_in: dict) -> dict:
        run_in.setdefault("verified_loop", {})["status"] = "pending_approval"
        return run_in

    patch_run_meta(folder, _pending)
    approve_verified_loop(folder)
    enable_mission_loop(folder, start_autonomous=True)

    def _bootstrap(run_in: dict) -> dict:
        ml = get_mission_loop(run_in)
        ml["enabled"] = True
        ml["phase"] = "CLARIFY"
        ml.setdefault("autonomous_segment", {"active": True})
        run_in["mission_loop"] = ml
        run_in["verified_loop"] = {"loop_goal": {"text": spec.goal_text}, "status": "approved"}
        return run_in

    patch_run_meta(folder, _bootstrap)
    run = read_run_meta(folder)
    record("clarify_phase", (run.get("mission_loop") or {}).get("phase") == "CLARIFY", "bootstrap CLARIFY")

    clarity_ok = clarity_threshold_met(run)
    record("clarity_threshold", clarity_ok, f"clarity_threshold_met={clarity_ok}")
    if live and clarity_ok:
        score = score_ambiguity(spec.goal_text)
        record("live_clarity_score", 0.0 <= score <= 1.0, f"score={score}")

    maybe_advance_mission(folder, scheduled=True)
    run = read_run_meta(folder)
    ml = run.get("mission_loop") or {}
    record("after_clarify", ml.get("phase") == "DISCUSS", f"phase={ml.get('phase')!r}")

    advance = maybe_advance_mission(folder, scheduled=True)
    run = read_run_meta(folder)
    ml = run.get("mission_loop") or {}
    record(
        "plan_gate",
        ml.get("phase") == "PLAN_GATE" and advance.get("status") == "forwarded",
        f"phase={ml.get('phase')!r} advance={advance!r}",
    )
    record(
        "goal_ledger",
        isinstance(run.get("goal_ledger"), list) and len(run.get("goal_ledger") or []) > 0,
        "goal_ledger events",
    )

    result["ok"] = all(c["ok"] for c in result["checks"])
    result["final_phase"] = ml.get("phase")
    result["consensus"] = run_c
    result["folder"] = str(folder)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sessions", type=Path, default=ROOT / "sessions")
    parser.add_argument("--agents", default="cursor,codex,claude", help="Comma-separated agent list")
    parser.add_argument("--mock", action="store_true", help="Use mock agents instead of live")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    selected_agents = [a.strip() for a in args.agents.split(",") if a.strip()]

    specs = [
        MissionSpec(
            name="jwt-auth",
            topic=("JWT validation in `src/auth.py` — agree retry/backoff before plan.md.\n[cat: quick]"),
            goal_text="Add JWT validation with retry in src/auth.py; verify with make test",
        ),
        MissionSpec(
            name="health-rate-limit",
            topic=(
                "Rate limit burst on `GET /api/health` in `app/server/routers/health.py`.\n"
                "Acceptance criteria: return 429 on burst.\n[cat: quick]"
            ),
            goal_text="Rate-limit GET /api/health in app/server/routers/health.py (429 on burst)",
        ),
    ]

    reports: list[dict[str, Any]] = []
    for spec in specs:
        spec.agents = selected_agents
        print(f"\n=== mission: {spec.name} ({'live' if not args.mock else 'mock'}) ===", file=sys.stderr)
        try:
            reports.append(run_mission(spec, sessions_root=args.sessions.expanduser(), live=not args.mock))
        except Exception as exc:
            reports.append({"name": spec.name, "ok": False, "error": str(exc), "checks": []})

    ok = all(r.get("ok") for r in reports)
    if args.json:
        print(json.dumps({"ok": ok, "missions": reports}, ensure_ascii=False, indent=2))
    else:
        for r in reports:
            status = "OK" if r.get("ok") else "FAIL"
            print(f"{status}: {r.get('name')} → {r.get('session_id', '?')} phase={r.get('final_phase')}")
            for row in r.get("checks") or []:
                mark = "✓" if row.get("ok") else "✗"
                print(f"  {mark} {row['name']}: {row['detail']}")
            if r.get("error"):
                print(f"  error: {r['error']}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
