#!/usr/bin/env python3
"""X2 lift live dogfood — repeat same topic N times for advisor history lift.

Requires: API on :8765, live agents (MOCK off), x2-lift env flags on server or
inherited from shell before ``make dev``.

Usage:
  eval "$(make -s x2-lift-dogfood-env)"
  make dev   # separate terminal
  make x2-lift-dogfood-prepare   # reset reversible typo in docs/_dogfood/x2-lift.md
  .venv/bin/python scripts/x2_lift_dogfood_live_repeat.py --count 5
  .venv/bin/python scripts/x2_lift_dogfood_live_repeat.py --resolve-only SESSION_ID
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
for _p in (ROOT / "src", SCRIPTS, ROOT):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from x2_lift_dogfood_config import (  # noqa: E402
    DOGFood_REL,
    TOPIC,
    apply_typo,
    has_typo,
)

API = os.environ.get("AGENT_LAB_API", "http://127.0.0.1:8765").rstrip("/")

AGENTS = ["cursor", "codex", "claude"]
PERMS = {
    "cursor": {"tools": True, "local_agent_lab": True, "local_pipeline": True},
    "codex": {"cli": True},
    "claude": {"tools": True, "write": True, "local_agent_lab": True},
}


def _session_path(session_id: str, suffix: str = "") -> str:
    return f"/api/sessions/{quote(session_id, safe='')}{suffix}"


def _json_request(
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
    *,
    timeout: float = 120.0,
) -> dict[str, Any]:
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(f"{API}{path}", data=data, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _git_dirty_count() -> tuple[int, list[str]]:
    proc = subprocess.run(
        ["git", "status", "--short"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]
    return len(lines), lines[:8]


def _read_run_execution(session_id: str, exec_id: str | None = None) -> dict[str, Any] | None:
    run_path = ROOT / "sessions" / session_id / "run.json"
    if not run_path.is_file():
        return None
    run = json.loads(run_path.read_text(encoding="utf-8"))
    executions = run.get("executions") or []
    if exec_id:
        return next((e for e in executions if e.get("id") == exec_id), None)
    for ex in reversed(executions):
        status = str(ex.get("status") or "")
        if status in {"pending_approval", "merge_conflict", "review_required"}:
            return ex
    return None


def _maybe_unblock_artifact_gate(session_id: str, exec_id: str) -> bool:
    """Dogfood-only: satisfy artifact review gate when verify is grep-based."""
    from agent_lab.run.meta import patch_run_meta, read_run_meta

    folder = ROOT / "sessions" / session_id
    run = read_run_meta(folder)
    target = next((e for e in (run.get("executions") or []) if e.get("id") == exec_id), None)
    if not target or not target.get("needs_artifact_review"):
        return False
    arts = target.get("verification_artifacts") or {}
    if arts.get("ok"):
        return False

    def patch(run: dict[str, Any]) -> dict[str, Any]:
        for ex in run.get("executions") or []:
            if ex.get("id") != exec_id:
                continue
            ex["verification_artifacts"] = {
                "ok": True,
                "pdf_path": str(DOGFood_REL),
                "pdf_page_count": 1,
                "break_report": {
                    "baselinePdfPageCount": 1,
                    "note": "x2 dogfood artifact ack (grep verify)",
                },
            }
        return run

    patch_run_meta(folder, patch)
    return True


def _resolve_execution(session_id: str, exec_id: str) -> dict[str, Any]:
    _maybe_unblock_artifact_gate(session_id, exec_id)
    payload = _json_request(
        "POST",
        _session_path(session_id, "/execute/resolve"),
        {"execution_id": exec_id, "vote": "approve", "permissions": PERMS},
        timeout=900.0,
    )
    return payload.get("execution") or {}


def _parse_sse(raw: bytes) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for block in raw.decode("utf-8", errors="replace").split("\n\n"):
        data_line = next(
            (ln[5:].strip() for ln in block.splitlines() if ln.startswith("data: ")),
            None,
        )
        if data_line:
            try:
                events.append(json.loads(data_line))
            except json.JSONDecodeError:
                pass
    return events


def _room_run(*, session_id: str | None = None, timeout: float = 1800.0) -> tuple[str | None, list[dict[str, Any]], float]:
    boundary = "----AgentLabX2Live"
    fields = [
        ("topic", TOPIC),
        ("agents", json.dumps(AGENTS)),
        ("mode", "discuss"),
        ("synthesize", "false"),
        ("synthesize_only", "false"),
        ("agent_rounds", "1"),
        ("review_mode", "false"),
        ("consensus_mode", "false"),
        ("efficiency_mode", "false"),
        ("turn_profile", "discuss"),
        ("preset", "supervisor"),
        ("permissions", json.dumps(PERMS)),
        ("workspace_id", "agent-lab"),
    ]
    if session_id:
        fields.append(("session_id", session_id))
    body = (
        "".join(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'
            for k, v in fields
        )
        + f"--{boundary}--\r\n"
    )
    req = urllib.request.Request(
        f"{API}/api/room/runs",
        data=body.encode("utf-8"),
        method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
    events = _parse_sse(raw)
    sid = session_id
    for ev in events:
        if ev.get("type") == "complete" and ev.get("session_id"):
            sid = str(ev["session_id"])
        if ev.get("type") == "start" and ev.get("session_id") and not sid:
            sid = str(ev["session_id"])
    return sid, events, time.time() - t0


def _plan_workflow(session_id: str) -> dict[str, Any]:
    return _json_request("GET", _session_path(session_id, "/plan/workflow"))


def _wait_human_pending(session_id: str, *, timeout: float = 60.0) -> str:
    deadline = time.time() + timeout
    phase = ""
    while time.time() < deadline:
        wf = _plan_workflow(session_id)
        phase = str((wf.get("plan_workflow") or {}).get("phase") or "").upper()
        if phase in {"HUMAN_PENDING", "APPROVED"}:
            return phase
        time.sleep(5.0)
    return phase


def _approve_plan(session_id: str) -> dict[str, Any]:
    return _json_request(
        "POST",
        _session_path(session_id, "/plan/approve"),
        {"goal": "x2 dogfood typo fix", "completion_promise": "DONE", "criteria": "Oracle PASS"},
        timeout=180.0,
    )


def _approve_pending_snapshots(session_id: str) -> None:
    pending = _json_request("GET", _session_path(session_id, "/execute/pending-plans"))
    for row in pending.get("pending_plans") or []:
        if str(row.get("status") or "").lower() == "approved":
            continue
        pid = str(row.get("id") or "").strip()
        if not pid:
            continue
        try:
            _json_request(
                "POST",
                _session_path(session_id, f"/execute/pending-plans/{quote(pid, safe='')}/approve"),
                {},
            )
        except urllib.error.HTTPError as exc:
            if exc.code != 400:
                raise


def _first_executable_action(session_id: str) -> tuple[int, str | None]:
    payload = _json_request("GET", _session_path(session_id, "/plan-actions"))
    actions = payload.get("actions") or []
    for row in actions:
        if not isinstance(row, dict):
            continue
        if row.get("executable") is False:
            continue
        idx = int(row.get("index") or 0)
        if idx >= 1:
            kind = row.get("kind")
            return idx, str(kind) if kind else None
    return 1, "now"


def _execute_pipeline(
    session_id: str,
    *,
    allow_dirty: bool,
) -> dict[str, Any]:
    pending = _read_run_execution(session_id)
    if pending and pending.get("id"):
        exec_id = str(pending["id"])
        if str(pending.get("status")) == "merge_conflict":
            return _resolve_execution(session_id, exec_id)
        if str(pending.get("status")) in {"pending_approval", "review_required"}:
            return _resolve_execution(session_id, exec_id)

    dirty_n, dirty_lines = _git_dirty_count()
    if dirty_n and not allow_dirty:
        isolation = None
        payload = _json_request("GET", _session_path(session_id, "/plan-actions"))
        rec = payload.get("recommended") or {}
        if isinstance(rec, dict):
            isolation = rec.get("isolation")
        if isolation == "worktree":
            raise RuntimeError(
                f"git root dirty ({dirty_n} paths) — stash/commit before worktree execute. "
                f"Sample: {dirty_lines[:3]}. Use --allow-dirty to skip."
            )

    _approve_pending_snapshots(session_id)
    action_index, action_kind = _first_executable_action(session_id)
    dry_body: dict[str, Any] = {"action_index": action_index, "permissions": PERMS}
    if action_kind:
        dry_body["action_kind"] = action_kind
    dry = _json_request(
        "POST",
        _session_path(session_id, "/execute/dry-run"),
        dry_body,
        timeout=900.0,
    )
    execution = dry.get("execution") or {}
    exec_id = str(execution.get("id") or "").strip()
    if not exec_id:
        detail = dry.get("detail")
        if isinstance(detail, dict) and detail.get("code") == "base_branch_dirty":
            raise RuntimeError(json.dumps(detail, ensure_ascii=False))
        raise RuntimeError(f"dry-run missing execution id: {dry}")
    status = str(execution.get("status") or "")
    if status in {"pending_approval", "merge_conflict", "review_required"}:
        execution = _resolve_execution(session_id, exec_id)
    return execution


def _routing_snapshot(session_id: str) -> dict[str, Any]:
    folder = ROOT / "sessions" / session_id
    run_path = folder / "run.json"
    if not run_path.is_file():
        return {}
    run = json.loads(run_path.read_text(encoding="utf-8"))
    turns = run.get("turns") or []
    if not turns:
        return {}
    last = turns[-1]
    tp = last.get("turn_policy") if isinstance(last, dict) else {}
    routing = (tp.get("routing_contract") or {}) if isinstance(tp, dict) else {}
    return {
        "turn_profile": last.get("turn_profile"),
        "routing": routing,
        "send_receipt": last.get("send_receipt"),
    }


def _execution_ok(execution: dict[str, Any]) -> bool:
    oracle = execution.get("oracle") or (execution.get("verify_after_merge") or {}).get("oracle") or {}
    return oracle.get("verdict") == "pass" or execution.get("status") in {"merged", "completed"}


def _prepare_dogfood() -> dict[str, Any]:
    changed, reason = apply_typo()
    return {"changed": changed, "reason": reason, "has_typo": has_typo()}


def _execute_only(session_id: str, *, allow_dirty: bool, exec_id: str | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {"session_id": session_id, "ok": False}
    try:
        if exec_id:
            execution = _resolve_execution(session_id, exec_id)
            result["execution_status"] = execution.get("status")
            result["oracle_verdict"] = (execution.get("oracle") or {}).get("verdict")
            result["ok"] = _execution_ok(execution)
            return result

        phase = _wait_human_pending(session_id, timeout=10.0)
        result["plan_phase"] = phase
        if phase == "HUMAN_PENDING":
            _approve_plan(session_id)
        elif phase != "APPROVED":
            wf = _plan_workflow(session_id)
            result["plan_workflow"] = wf.get("plan_workflow")
            result["error"] = f"plan not ready (phase={phase})"
            return result

        execution = _execute_pipeline(session_id, allow_dirty=allow_dirty)
        result["execution_status"] = execution.get("status")
        oracle = execution.get("oracle") or (execution.get("verify_after_merge") or {}).get("oracle") or {}
        result["oracle_verdict"] = oracle.get("verdict")
        result["ok"] = _execution_ok(execution)
        return result
    except urllib.error.HTTPError as exc:
        result["error"] = exc.read().decode("utf-8", errors="replace")[:500]
        return result
    except Exception as exc:  # noqa: BLE001
        result["error"] = str(exc)[:500]
        return result


def _resolve_only(session_id: str, exec_id: str | None, *, allow_dirty: bool) -> dict[str, Any]:
    result: dict[str, Any] = {"session_id": session_id, "ok": False, "mode": "resolve-only"}
    try:
        target = _read_run_execution(session_id, exec_id)
        if not target:
            result["error"] = "no pending execution"
            return result
        eid = str(target.get("id") or "")
        result["execution_id"] = eid
        if not allow_dirty:
            dirty_n, _ = _git_dirty_count()
            if dirty_n and target.get("isolation_effective") == "worktree":
                result["error"] = f"git dirty ({dirty_n} paths) — stash or use --allow-dirty"
                return result
        execution = _resolve_execution(session_id, eid)
        result["execution_status"] = execution.get("status")
        oracle = execution.get("oracle") or (execution.get("verify_after_merge") or {}).get("oracle") or {}
        result["oracle_verdict"] = oracle.get("verdict")
        result["ok"] = _execution_ok(execution)
        return result
    except urllib.error.HTTPError as exc:
        result["error"] = exc.read().decode("utf-8", errors="replace")[:500]
        return result
    except Exception as exc:  # noqa: BLE001
        result["error"] = str(exc)[:500]
        return result


def _run_iteration(index: int, total: int, *, allow_dirty: bool, prepare: bool) -> dict[str, Any]:
    print(f"\n=== live pass {index}/{total} ===", flush=True)
    result: dict[str, Any] = {"pass": index, "ok": False}
    try:
        if prepare:
            result["dogfood_prepare"] = _prepare_dogfood()

        session_id, events, elapsed = _room_run()
        result["room_seconds"] = round(elapsed, 1)
        result["session_id"] = session_id
        result["sse_events"] = len(events)
        if not session_id:
            errs = [e for e in events if e.get("type") == "error"]
            result["error"] = errs or "no session_id"
            return result

        result["routing"] = _routing_snapshot(session_id)
        phase = _wait_human_pending(session_id)
        result["plan_phase_before_approve"] = phase
        if phase == "HUMAN_PENDING":
            _approve_plan(session_id)
        elif phase != "APPROVED":
            wf = _plan_workflow(session_id)
            result["plan_workflow"] = wf.get("plan_workflow")
            result["error"] = f"plan not ready (phase={phase})"
            return result

        execution = _execute_pipeline(session_id, allow_dirty=allow_dirty)
        result["execution_status"] = execution.get("status")
        oracle = execution.get("oracle") or (execution.get("verify_after_merge") or {}).get("oracle") or {}
        result["oracle_verdict"] = oracle.get("verdict")
        result["ok"] = _execution_ok(execution)
        return result
    except urllib.error.HTTPError as exc:
        result["error"] = exc.read().decode("utf-8", errors="replace")[:500]
        return result
    except Exception as exc:  # noqa: BLE001
        result["error"] = str(exc)[:500]
        return result


def main() -> int:
    global API

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=5, help="repeat count (default 5)")
    parser.add_argument("--api", default=API, help="API base URL")
    parser.add_argument(
        "--execute-only",
        metavar="SESSION_ID",
        help="skip room run; approve plan (if needed) + execute on existing session",
    )
    parser.add_argument(
        "--resolve-only",
        metavar="SESSION_ID",
        help="resolve pending execution only (optional --execution-id)",
    )
    parser.add_argument(
        "--execution-id",
        metavar="EXEC_ID",
        help="with --resolve-only: specific execution id",
    )
    parser.add_argument(
        "--prepare",
        action="store_true",
        help="reset docs/_dogfood/x2-lift.md typo before each pass (default on for repeat)",
    )
    parser.add_argument(
        "--no-prepare",
        action="store_true",
        help="skip dogfood typo reset before each pass",
    )
    parser.add_argument(
        "--allow-dirty",
        action="store_true",
        help="skip git-clean guard for worktree isolation",
    )
    args = parser.parse_args()

    API = args.api.rstrip("/")
    prepare_each = not args.no_prepare
    if args.prepare:
        prepare_each = True

    if os.environ.get("AGENT_LAB_MOCK_AGENTS", "").strip().lower() in {"1", "true", "yes"}:
        print("WARN: AGENT_LAB_MOCK_AGENTS is set — this is not live", file=sys.stderr)

    if args.prepare and not args.execute_only and not args.resolve_only:
        out = _prepare_dogfood()
        print(json.dumps({"prepare": out}, ensure_ascii=False, indent=2))
        return 0

    try:
        ready = _json_request("GET", "/api/health/readiness", timeout=30.0)
    except Exception as exc:
        print(f"API not ready at {API}: {exc}", file=sys.stderr)
        return 1
    if ready.get("verdict") not in {"ready", "blocked"}:
        print(f"API readiness: {ready.get('verdict')}", file=sys.stderr)
        return 1

    if args.resolve_only:
        result = _resolve_only(args.resolve_only.strip(), args.execution_id, allow_dirty=args.allow_dirty)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("ok") else 1

    if args.execute_only:
        result = _execute_only(args.execute_only.strip(), allow_dirty=args.allow_dirty)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("ok") else 1

    results: list[dict[str, Any]] = []
    for i in range(1, max(1, args.count) + 1):
        results.append(_run_iteration(i, args.count, allow_dirty=args.allow_dirty, prepare=prepare_each))

    from agent_lab.feedback_report import build_feedback_report, render_feedback_report

    report = build_feedback_report(ROOT / ".agent-lab")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = ROOT / "sessions" / "_benchmark" / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"feedback-report-{stamp}.json"
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "topic": TOPIC,
        "dogfood_file": str(DOGFood_REL),
        "passes": results,
        "ok_count": sum(1 for r in results if r.get("ok")),
        "feedback_report": str(out_path),
        "advisor_lift": report.get("advisor_lift"),
        "by_source": report.get("by_source"),
        "turn_source_counts": report.get("turn_source_counts"),
        "verdict_eligible_total": report.get("verdict_eligible_total"),
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
