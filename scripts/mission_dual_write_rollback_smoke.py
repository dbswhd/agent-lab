"""DUAL_WRITE=0 rollback 스모크 — live API 기준."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT, ROOT / "src"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

    sys.path.insert(0, str(ROOT / "scripts"))
    from mission_dual_write_live_routes import _http_json, _init_session


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    parser.add_argument("--sessions", type=Path, required=True)
    parser.add_argument("--mirrored-session", required=True, help="session already dual-written")
    parser.add_argument("--fresh-session", default="dw-cohort-rb-fresh")
    args = parser.parse_args()

    base = args.base_url.rstrip("/")
    from agent_lab.plan.workflow_state import set_plan_workflow_phase

    fresh = _init_session(args.sessions, args.fresh_session)
    set_plan_workflow_phase(fresh, "HUMAN_PENDING")
    fresh_status, fresh_body = _http_json(
        "POST", f"{base}/api/sessions/{args.fresh_session}/plan/approve", {"goal": "rollback"}
    )
    journal = fresh / ".agent-lab" / "mission-events.jsonl"

    mirrored_status, mirrored_body = _http_json(
        "GET", f"{base}/api/sessions/{args.mirrored_session}/mission/read-model"
    )

    report: dict[str, Any] = {
        "kind": "rollback_smoke",
        "fresh_session": args.fresh_session,
        "fresh_approve_status": fresh_status,
        "fresh_dual_write_enabled": (fresh_body.get("mission_dual_write") or {}).get("enabled"),
        "fresh_mirrored": (fresh_body.get("mission_dual_write") or {}).get("mirrored"),
        "fresh_journal_created": journal.is_file(),
        "mirrored_session": args.mirrored_session,
        "mirrored_read_model_status": mirrored_status,
        "mirrored_still_migrated": mirrored_body.get("migrated"),
    }
    report["pass"] = (
        fresh_status == 200
        and report["fresh_dual_write_enabled"] is False
        and report["fresh_mirrored"] is False
        and report["fresh_journal_created"] is False
        and mirrored_status == 200
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
