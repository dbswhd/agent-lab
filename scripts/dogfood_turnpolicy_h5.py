#!/usr/bin/env python3
"""Dogfood H5 — mock turn on TurnPolicy session copy; verify shipped KPIs."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

DEFAULT_SOURCE = (
    ROOT / "sessions" / "2026-06-28-name-turnpolicy-wave-f-overview-plan-onoffcompos"
)
H5_MESSAGE = (
    "Dogfood H5 — C9 fix 이후 session_metrics · CLARIFY inbox · synthesis lead 검증"
)


def _seed_session(folder: Path) -> None:
    from agent_lab.run.meta import patch_run_meta, read_run_meta

    plan = folder / "plan.md"
    if not plan.read_text(encoding="utf-8").strip():
        plan.write_text(
            "## 쟁점 / 미결정\n- S1 MCP vs Wave F 우선순위 fork\n",
            encoding="utf-8",
        )

    def _patch(run: dict[str, Any]) -> dict[str, Any]:
        run["room_preset"] = "supervisor"
        run["team_lead"] = "cursor"
        run["turn_leads"] = {**(run.get("turn_leads") or {}), "5": "cursor"}
        run["agents"] = ["cursor", "claude"]
        pw = run.get("plan_workflow") or {}
        pw["enabled"] = True
        pw["phase"] = "CLARIFY"
        run["plan_workflow"] = pw
        return run

    patch_run_meta(folder, _patch)
    _ = read_run_meta(folder)


def _verify_kpis(
    folder: Path,
    *,
    turn_lead_expected: str,
    h5_human_prefix: str,
) -> tuple[list[str], dict[str, Any]]:
    from agent_lab.human_inbox import inbox_items
    from agent_lab.run.meta import read_run_meta
    from agent_lab.room.session_persist import load_session_messages
    from agent_lab.session.metrics_payload import build_session_metrics_payload

    errors: list[str] = []
    report: dict[str, Any] = {}

    run = read_run_meta(folder)
    report["room_preset"] = run.get("room_preset")
    report["turn_policy"] = run.get("turn_policy")
    report["plan_workflow_phase"] = (run.get("plan_workflow") or {}).get("phase")
    inbox = inbox_items(run)
    report["human_inbox_count"] = len(inbox)

    if run.get("room_preset") != "supervisor":
        errors.append(f"room_preset expected supervisor, got {run.get('room_preset')!r}")

    tp = run.get("turn_policy")
    if not isinstance(tp, dict) or not tp:
        errors.append("turn_policy missing on run.json after H5")

    if not inbox:
        errors.append("CLARIFY harvest: human_inbox still empty")
    else:
        report["inbox_triggers"] = [it.get("trigger") for it in inbox[:5]]

    agent_lab = folder / ".agent-lab"
    overlays = sorted(p.name for p in agent_lab.glob("*")) if agent_lab.is_dir() else []
    report["agent_lab_overlays"] = overlays
    if not any("session-metrics" in name for name in overlays):
        errors.append("session_metrics overlay missing under .agent-lab/")
    try:
        metrics = build_session_metrics_payload(folder)
        report["session_metrics_kpi_keys"] = list((metrics.get("scores") or {}).keys())[:6]
    except Exception as exc:
        errors.append(f"session_metrics payload failed: {exc}")

    msgs = load_session_messages(folder)
    h5_idx = next(
        (i for i, m in enumerate(msgs) if m.role == "user" and h5_human_prefix in (m.content or "")),
        -1,
    )
    h5_msgs = msgs[h5_idx:] if h5_idx >= 0 else msgs[-10:]
    leaks = [
        m
        for m in h5_msgs
        if m.role == "agent"
        and (
            "prepare_turn_policy" in (m.content or "")
            or "I am ready to act" in (m.content or "")
        )
    ]
    report["h5_monologue_leaks"] = len(leaks)
    if leaks:
        errors.append(f"quality gate: {len(leaks)} H5 agent replies leak SDK monologue")

    turns = run.get("turns") or []
    if turns:
        last = turns[-1]
        report["last_turn"] = {
            "status": last.get("status"),
            "turn_lead": last.get("turn_lead"),
            "send_receipt": last.get("send_receipt"),
            "turn_policy": last.get("turn_policy"),
        }
        if last.get("status") == "cancelled":
            errors.append("H5 turn status cancelled")
        if last.get("turn_lead") != turn_lead_expected:
            errors.append(
                f"turn_lead expected {turn_lead_expected}, got {last.get('turn_lead')!r}",
            )

    phase = (run.get("plan_workflow") or {}).get("phase")
    if phase == "CLARIFY":
        report["fsm_note"] = "still CLARIFY (inbox pending before DRAFT)"
    elif phase == "DRAFT":
        report["fsm_note"] = "C9: advanced to DRAFT"

    return errors, report


def run_h5(*, source: Path, in_place: bool) -> tuple[int, dict[str, Any]]:
    os.environ.setdefault("AGENT_LAB_MOCK_AGENTS", "1")
    os.environ.setdefault("AGENT_LAB_TURN_POLICY", "1")
    os.environ.setdefault("AGENT_LAB_SESSION_METRICS_MCP", "1")

    if in_place:
        folder = source
    else:
        tmp = Path(tempfile.mkdtemp(prefix="agent-lab-h5-"))
        folder = tmp / source.name
        shutil.copytree(source, folder)

    _seed_session(folder)

    from agent_lab.room import continue_room_round
    from agent_lab.room.preset import preset_turn_profile

    profile = preset_turn_profile("supervisor")
    messages, _plan = continue_room_round(
        folder,
        H5_MESSAGE,
        agents=["cursor", "claude"],
        synthesize=False,
        parallel_rounds=1,
        turn_profile=profile,
        consensus_mode=True,
    )
    agent_replies = [m for m in messages if m.role == "agent"]
    if len(agent_replies) < 1:
        return 1, {"error": "no agent replies", "folder": str(folder)}

    errors, report = _verify_kpis(
        folder,
        turn_lead_expected="cursor",
        h5_human_prefix="Dogfood H5",
    )
    report["folder"] = str(folder)
    report["agent_replies"] = len(agent_replies)
    report["errors"] = errors
    return (1 if errors else 0), report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument(
        "--in-place",
        action="store_true",
        help="Mutate source session (default: temp copy)",
    )
    args = parser.parse_args()
    if not args.source.is_dir():
        print(f"FAIL: session not found: {args.source}", file=sys.stderr)
        return 1

    code, report = run_h5(source=args.source.expanduser().resolve(), in_place=args.in_place)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if code:
        for err in report.get("errors") or []:
            print(f"FAIL: {err}", file=sys.stderr)
        return code
    print("OK: dogfood H5 KPIs passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
