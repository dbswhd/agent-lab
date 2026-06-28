#!/usr/bin/env python3
"""Mock pipeline dogfood: AGENT_LAB_PIPELINE=1 CLARIFY→DISCUSS→consensus→PLAN_GATE."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

os.environ.setdefault("AGENT_LAB_MOCK_AGENTS", "1")
os.environ.setdefault("AGENT_LAB_MISSION_LOOP", "1")
os.environ.setdefault("AGENT_LAB_PIPELINE", "1")


def _utc_slug() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def _checks() -> list[tuple[str, bool, str]]:
    return []


def _install_consensus_mock() -> None:
    """Mock agents that reach consensus (PROPOSE + ENDORSE envelopes)."""
    import json

    from agent_lab.agents.registry import AgentReply

    per_agent: dict[str, int] = {}

    def patched(agent, system, user, **kwargs):
        if kwargs.get("scribe"):
            return AgentReply(text="## Plan\n\n- mock\n")
        n = per_agent.get(agent, 0) + 1
        per_agent[agent] = n

        def envelope(act: str, body: str) -> AgentReply:
            payload = json.dumps({"act": act, "refs": [], "confidence": 0.9})
            return AgentReply(text=f"```agent-envelope\n{payload}\n```\n{body}")

        if agent == "cursor" and n == 1:
            return envelope("PROPOSE", "Use src/auth.py JWT middleware with retry.")
        return envelope("ENDORSE", "Agreed.")

    import agent_lab.agents.registry as registry

    registry.call_agent_reply = patched  # type: ignore[method-assign]
    registry.call_agent = lambda agent, system, user, **kw: patched(agent, system, user, **kw).text


def run_pipeline_dogfood(*, sessions_root: Path, session_id: str | None = None) -> tuple[Path, list[dict[str, object]]]:
    from agent_lab.mission.loop import get_mission_loop, pipeline_enabled
    from agent_lab.clarity import clarity_threshold_met, score_ambiguity
    from agent_lab.consensus_gate import consensus_gate_met
    from agent_lab.mission.advance import maybe_advance_mission
    from agent_lab.mission.loop import enable_mission_loop
    from agent_lab.run.meta import patch_run_meta, read_run_meta

    checks: list[dict[str, object]] = []

    def record(name: str, ok: bool, detail: str) -> None:
        checks.append({"name": name, "ok": ok, "detail": detail})
        if not ok:
            raise RuntimeError(f"{name}: {detail}")

    record("pipeline_flag", pipeline_enabled(), "AGENT_LAB_PIPELINE must be enabled")

    _install_consensus_mock()
    from agent_lab import room

    sid = session_id or f"pipeline-dogfood-{_utc_slug()}"
    folder = sessions_root / sid
    folder.mkdir(parents=True, exist_ok=True)

    topic = "JWT validation in `src/auth.py` — agree on retry path before plan.md.\n[cat: quick]"
    folder, _messages, _plan = room.run_room(
        topic,
        agents=["cursor", "codex", "claude"],
        synthesize=False,
        sessions_base=sessions_root,
        session_folder=folder,
        consensus_mode=True,
    )
    run = read_run_meta(folder)
    turn_consensus = (run.get("turns") or [{}])[0].get("consensus") if run.get("turns") else None
    run_consensus = run.get("consensus") or {}
    record(
        "turn_consensus_reached",
        isinstance(turn_consensus, dict) and turn_consensus.get("status") == "reached",
        f"turn consensus={turn_consensus!r}",
    )
    record(
        "run_consensus_persisted",
        run_consensus.get("status") == "reached",
        f"run.consensus={run_consensus!r}",
    )
    record(
        "consensus_gate_met",
        consensus_gate_met(run),
        "consensus_gate should pass after Room persist",
    )

    enable_mission_loop(folder, start_autonomous=True)

    def _bootstrap_clarify(run: dict) -> dict:
        ml = get_mission_loop(run)
        ml["enabled"] = True
        ml["phase"] = "CLARIFY"
        ml.setdefault("autonomous_segment", {"active": True})
        run["mission_loop"] = ml
        run["verified_loop"] = {"loop_goal": {"text": "fix JWT validation in src/auth.py"}}
        return run

    patch_run_meta(folder, _bootstrap_clarify)
    run = read_run_meta(folder)
    ml = run.get("mission_loop") or {}
    record("clarify_bootstrap", ml.get("phase") == "CLARIFY", f"phase={ml.get('phase')!r}")

    vague_run = dict(run)
    vague_run["topic"] = "make the app better"
    vague_run["verified_loop"] = {"loop_goal": {"text": "make the app better"}}
    record(
        "clarity_vague_blocked",
        not clarity_threshold_met(vague_run),
        "vague goal should stay in CLARIFY",
    )
    anchored_run = dict(run)
    anchored_run["verified_loop"] = {"loop_goal": {"text": "fix JWT in src/auth.py"}}
    record(
        "clarity_anchored_pass",
        clarity_threshold_met(anchored_run),
        "anchored goal should pass clarity gate",
    )

    maybe_advance_mission(folder, scheduled=True)
    run = read_run_meta(folder)
    ml = run.get("mission_loop") or {}
    record("clarify_to_discuss", ml.get("phase") == "DISCUSS", f"phase={ml.get('phase')!r}")
    record("mode_route_recorded", isinstance(ml.get("mode_route"), dict), f"mode_route={ml.get('mode_route')!r}")
    record("goal_ledger_present", isinstance(run.get("goal_ledger"), list), "goal_ledger missing")

    advance = maybe_advance_mission(folder, scheduled=True)
    run = read_run_meta(folder)
    ml = run.get("mission_loop") or {}
    record(
        "discuss_to_plan_gate",
        ml.get("phase") == "PLAN_GATE" and advance.get("status") == "forwarded",
        f"phase={ml.get('phase')!r} advance={advance!r}",
    )

    def _clarify_reset(run_in: dict) -> dict:
        m = run_in.setdefault("mission_loop", {})
        m["phase"] = "CLARIFY"
        m["enabled"] = True
        m.setdefault("autonomous_segment", {"active": True})
        run_in["topic"] = "improve reliability"
        run_in["verified_loop"] = {"loop_goal": {"text": "improve reliability"}}
        return run_in

    patch_run_meta(folder, _clarify_reset)
    out = maybe_advance_mission(folder, scheduled=True)
    run = read_run_meta(folder)
    record(
        "clarity_pending_guard",
        (run.get("mission_loop") or {}).get("phase") == "CLARIFY" and out.get("reason") == "clarity_pending",
        f"out={out!r}",
    )

    mock_score = score_ambiguity("make it better")
    record("mock_scorer_vague", mock_score == 0.8, f"score={mock_score}")

    return folder, checks


def verify_live_scorer_path() -> tuple[bool, str]:
    """Exercise clarity.score_ambiguity without mock agents when configured."""
    prev = os.environ.get("AGENT_LAB_MOCK_AGENTS")
    os.environ["AGENT_LAB_MOCK_AGENTS"] = "0"
    try:
        from agent_lab.agents.registry import available_agents
        from agent_lab.clarity import score_ambiguity

        agents = available_agents()
        if not agents:
            return True, "skip: no live agents configured"
        score = score_ambiguity("improve holistic user experience without concrete files")
        if not (0.0 <= score <= 1.0):
            return False, f"score out of range: {score}"
        return True, f"live scorer ok via {agents[0]} score={score}"
    finally:
        if prev is None:
            os.environ.pop("AGENT_LAB_MOCK_AGENTS", None)
        else:
            os.environ["AGENT_LAB_MOCK_AGENTS"] = prev


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sessions", type=Path, default=ROOT / "sessions")
    parser.add_argument("--session-id", default=None)
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--live-scorer",
        action="store_true",
        help="Also call clarity.score_ambiguity with AGENT_LAB_MOCK_AGENTS=0 when agents exist",
    )
    args = parser.parse_args()

    checks: list[dict[str, object]] = []
    try:
        folder, checks = run_pipeline_dogfood(
            sessions_root=args.sessions.expanduser(),
            session_id=args.session_id,
        )
        if args.live_scorer:
            ok, detail = verify_live_scorer_path()
            checks.append({"name": "live_scorer_path", "ok": ok, "detail": detail})
            if not ok:
                raise RuntimeError(detail)
    except RuntimeError as exc:
        payload = {"ok": False, "error": str(exc), "checks": checks}
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(f"FAIL: {exc}", file=sys.stderr)
        return 1

    payload = {"ok": True, "session_id": folder.name, "checks": checks}
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"OK: pipeline dogfood — {folder.name}")
        for row in checks:
            mark = "✓" if row["ok"] else "✗"
            print(f"  {mark} {row['name']}: {row['detail']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
