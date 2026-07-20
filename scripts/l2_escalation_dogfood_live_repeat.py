#!/usr/bin/env python3
"""L2 escalation live dogfood — N4-D3 escalation_rate_by_level sample gate.

Reuses the X2-lift room/plan/execute cycle (reversible single-line docs typo,
already the project's sanctioned low-risk repeat fixture) but promotes each
session's autonomy ceiling to L2 right after the session is created, so the
execute-phase outcome row gets tagged ``autonomy_level=L2`` for real instead
of staying L0/L1. See autonomy_ladder.record_autonomy_transition — a promotion
to L2 now auto-provisions a trust_budget (10/10, docs_only/test_only/
single_file) when none is set yet, which is what makes the level *effective*
and not just a ceiling label.

Room composition is NOT pinned here — it inherits x2_lift_dogfood_live_repeat's
AGENTS (empty by default), so the server falls back to the operator's own
configured default composition.

The X2-lift fixture requires ``AGENT_LAB_EXECUTE_INBOX=0`` (nested-Cursor
propose_build), which also gates the discuss-lane ``ask_human`` MCP for most
plan-workflow phases (see inbox.mcp_policy.discuss_inbox_mcp_lane_enabled).
HUMAN_PENDING — the phase where an L2-promoted peer asks Human for GO
approval — is independently controllable via ``AGENT_LAB_PLAN_INBOX=1``
(plan_workflow_wants_human_pending_inbox_mcp); set it alongside EXECUTE_INBOX=0
or the room falls back to prose-only Human requests the API can't consume,
and repeated plan-retries will drift into peers self-applying the fixture fix.

Usage:
  eval "$(make -s dogfood-track-env)"
  export AGENT_LAB_PLAN_INBOX=1   # HUMAN_PENDING ask_human despite EXECUTE_INBOX=0
  make api   # restart API after changing env
  .venv/bin/python scripts/l2_escalation_dogfood_live_repeat.py --count 10
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
for _p in (ROOT / "src", SCRIPTS, ROOT):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import x2_lift_dogfood_live_repeat as x2  # noqa: E402

# A dynamically-composed room (no pinned roster) may settle a discuss round on a
# conversational reply instead of the structured plan.md the execute pipeline
# needs (## Must / ## Parallel waves). Blind-approving that stub 400s at
# dry-run with an empty action list — so wait for real structure instead of a
# fixed round count, and give the room a bounded number of continuation turns
# to get there before giving up.
PLAN_STRUCTURE_MARKERS = ("## Must", "## Parallel waves")
MAX_PLAN_RETRIES = 2


def _promote_l2(session_id: str) -> dict:
    return x2._json_request(
        "PATCH",
        x2._session_path(session_id, "/autonomy"),
        {"level": "L2", "reason": "l2_dogfood_live_repeat"},
        timeout=60.0,
    )


def _plan_structured(session_id: str) -> bool:
    plan_path = ROOT / "sessions" / session_id / "plan.md"
    if not plan_path.is_file():
        return False
    try:
        text = plan_path.read_text(encoding="utf-8")
    except OSError:
        return False
    return all(marker in text for marker in PLAN_STRUCTURE_MARKERS)


def _wait_approved_grace(session_id: str, *, timeout: float = 30.0) -> str:
    """auto_approve_gate can flip HUMAN_PENDING -> APPROVED a few seconds after
    plan_workflow settles (observed: 3s lag on a real L2-promoted low-risk
    plan) — a multi-agent room's plan.md doesn't always match the solo-agent
    template (## Must / ## Parallel waves), so give the real approval signal a
    short grace window instead of trusting a text-marker heuristic alone."""
    deadline = time.time() + timeout
    phase = "HUMAN_PENDING"
    while time.time() < deadline:
        wf = x2._plan_workflow(session_id)
        phase = str((wf.get("plan_workflow") or {}).get("phase") or "").upper()
        if phase == "APPROVED":
            return phase
        time.sleep(3.0)
    return phase


def _retry_topic(retry_num: int) -> str:
    """Continuation message for a not-yet-structured plan.md.

    Resubmitting x2.TOPIC verbatim gives the room no signal that this is a
    retry — by round 2-3 kimi_work reads it as "already handled" and reverts
    the typo directly in the discuss turn instead of producing plan.md, which
    is exactly the failure this fixture is trying to sample (N4-D3 L2 gate).
    Naming the retry and the missing structure explicitly keeps the ask
    distinct from the original turn."""
    return (
        f"[재시도 {retry_num}/{MAX_PLAN_RETRIES}] 이전 라운드에서 plan.md가 아직 "
        "`## Must` / `## Parallel waves` 구조로 작성되지 않았습니다. docs/_dogfood/x2-lift.md "
        "오타를 discuss 턴에서 직접 되돌리지 말고, propose_build로 구조화된 plan을 다시 제출해 "
        "승인 단계까지 진행해 주세요."
    )


def _ensure_structured_plan(session_id: str, *, room_timeout: float) -> dict:
    """Poll for HUMAN_PENDING; if plan.md isn't structured yet, resubmit a
    continuation turn on the same session (instead of blind-approving a
    conversational stub) up to MAX_PLAN_RETRIES times. phase == APPROVED
    always short-circuits as ready, regardless of plan.md's shape."""
    info: dict = {"retries": 0}
    phase = x2._wait_human_pending(session_id, timeout=10.0)
    while phase == "HUMAN_PENDING" and not _plan_structured(session_id) and info["retries"] < MAX_PLAN_RETRIES:
        info["retries"] += 1
        print(
            f"    plan.md not structured yet (retry {info['retries']}/{MAX_PLAN_RETRIES}) — continuing session",
            flush=True,
        )
        x2._room_run(
            session_id=session_id,
            timeout=room_timeout,
            topic_override=_retry_topic(info["retries"]),
        )
        phase = x2._wait_human_pending(session_id, timeout=x2.DEFAULT_PLAN_WAIT_TIMEOUT)
    if phase == "HUMAN_PENDING" and not _plan_structured(session_id):
        phase = _wait_approved_grace(session_id)
    info["phase"] = phase
    info["structured"] = phase == "APPROVED" or _plan_structured(session_id)
    return info


def _run_iteration(index: int, total: int, *, allow_dirty: bool, room_timeout: float) -> dict:
    print(f"\n=== L2 dogfood pass {index}/{total} ===", flush=True)
    result: dict = {"pass": index, "ok": False}
    try:
        result["dogfood_prepare"] = x2._prepare_dogfood()

        session_id, events, elapsed, stream_note = x2._room_run(timeout=room_timeout)
        result["room_seconds"] = round(elapsed, 1)
        result["session_id"] = session_id
        result["sse_events"] = len(events)
        if stream_note:
            result["room_stream"] = stream_note
        if not session_id:
            errs = [e for e in events if e.get("type") == "error"]
            result["error"] = errs or "no session_id"
            return result

        autonomy = _promote_l2(session_id)
        result["autonomy"] = (autonomy.get("autonomy") or {}).get("effective_level")
        result["trust_budget"] = (autonomy.get("autonomy") or {}).get("trust_budget")

        plan_check = _ensure_structured_plan(session_id, room_timeout=room_timeout)
        result["plan_check"] = plan_check
        if not plan_check["structured"]:
            result["error"] = (
                f"plan never structured after {plan_check['retries']} continuation retries "
                f"(phase={plan_check.get('phase')})"
            )
            return result

        result.update(x2._finish_pass(session_id, allow_dirty=allow_dirty))
        return result
    except urllib.error.HTTPError as exc:
        result["error"] = exc.read().decode("utf-8", errors="replace")[:500]
        return result
    except Exception as exc:  # noqa: BLE001
        result["error"] = str(exc)[:500]
        return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=10, help="repeat count (default 10 — N4-D3 needs n>=10)")
    parser.add_argument("--allow-dirty", action="store_true")
    parser.add_argument("--room-timeout", type=float, default=x2.DEFAULT_ROOM_TIMEOUT)
    args = parser.parse_args()

    try:
        ready = x2._json_request("GET", "/api/health/readiness", timeout=30.0)
    except Exception as exc:  # noqa: BLE001
        print(f"API not ready at {x2.API}: {exc}", file=sys.stderr)
        return 1
    if ready.get("verdict") not in {"ready", "blocked"}:
        print(f"API readiness: {ready.get('verdict')}", file=sys.stderr)
        return 1

    results = [
        _run_iteration(i, args.count, allow_dirty=args.allow_dirty, room_timeout=args.room_timeout)
        for i in range(1, max(1, args.count) + 1)
    ]

    from agent_lab.feedback_report import build_feedback_report, render_feedback_report

    report = build_feedback_report(ROOT / ".agent-lab")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = ROOT / "sessions" / "_benchmark" / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"l2-dogfood-report-{stamp}.json"
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "passes": results,
        "ok_count": sum(1 for r in results if r.get("ok")),
        "l2_count": sum(1 for r in results if r.get("autonomy") == "L2"),
        "feedback_report": str(out_path),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print("\n" + render_feedback_report(report))

    failed = [r for r in results if not r.get("ok")]
    if failed:
        print(f"\n{len(failed)}/{len(results)} passes did not complete execute+oracle", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
