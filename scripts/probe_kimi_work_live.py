#!/usr/bin/env python3
"""Live Kimi Work smoke: daimon probe, workspace bind, one short turn.

Requires Kimi Work credentials (daimon-share config). Uses Kimi.app daimon when running, else spawns headless.

Usage:
  .venv/bin/python scripts/probe_kimi_work_live.py
  .venv/bin/python scripts/probe_kimi_work_live.py --workspace /path/to/repo
  .venv/bin/python scripts/probe_kimi_work_live.py --prompt "Say hi in one sentence."
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe live Kimi Work daimon + workspace + turn")
    parser.add_argument(
        "--workspace",
        type=Path,
        default=ROOT,
        help="Directory to bind via workspace.openProject (default: repo root)",
    )
    parser.add_argument(
        "--prompt",
        default="Reply with exactly: kimi-work-probe-ok",
        help="User text for conversations.send",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON summary on stdout",
    )
    parser.add_argument(
        "--envelope-probe",
        action="store_true",
        help="Run Loop envelope readiness probe (structured speech act) after turn probe",
    )
    args = parser.parse_args()

    if os.getenv("AGENT_LAB_MOCK_AGENTS", "").strip().lower() in {"1", "true", "yes", "on"}:
        print("ERROR: unset AGENT_LAB_MOCK_AGENTS for live probe", file=sys.stderr)
        return 2

    from agent_lab.kimi_control_client import probe_control, rpc, send_turn
    from agent_lab.kimi_work_workspace import open_workspace

    bridge, err = probe_control()
    if bridge != "ok":
        print(f"probe_control failed: {err}", file=sys.stderr)
        return 1

    ws = args.workspace.expanduser().resolve()
    if not ws.is_dir():
        print(f"workspace not a directory: {ws}", file=sys.stderr)
        return 1

    open_result = open_workspace(ws)
    caps = rpc("capabilities.get", {})
    from agent_lab.kimi_work_session import extract_conversation_key

    created = rpc(
        "conversations.create",
        {"sessionKey": "main", "title": "agent-lab-probe"},
    )
    conv_key = extract_conversation_key(created)

    pushes: list[dict[str, str]] = []

    def on_push(method: str, payload: dict) -> None:
        pushes.append({"method": method, "keys": ",".join(sorted(payload.keys()))})

    body = send_turn(
        conversation_key=conv_key,
        text=str(args.prompt),
        system="agent-lab live probe — reply briefly",
        on_push=on_push,
    )

    summary = {
        "bridge": bridge,
        "workspace": str(ws),
        "open": open_result,
        "capabilities": caps,
        "conversationKey": conv_key,
        "reply_chars": len(body),
        "reply_preview": body[:200],
        "push_count": len(pushes),
        "pushes": pushes[:20],
    }

    if args.envelope_probe:
        from agent_lab.model_policy_probe import _probe_substitute_envelope

        summary["envelope_probe_ok"] = _probe_substitute_envelope("kimi_work", "k2p6")
        if not summary["envelope_probe_ok"]:
            print("envelope probe FAILED", file=sys.stderr)
            return 1

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print("Kimi Work live probe OK")
        print(f"  workspace: {ws}")
        print(f"  conversation: {conv_key}")
        if body.strip():
            print(f"  reply ({len(body)} chars): {body[:120]!r}")
        else:
            print(f"  reply (0 chars) — {len(pushes)} pushes (tool-only or text in snapshot parts only)")
        print(f"  pushes: {len(pushes)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
