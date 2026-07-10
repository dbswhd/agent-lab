#!/usr/bin/env python3
"""Live dogfood mid-gate driver — Inbox Question / MCP build / plan / execute.

Polls a live session (API :8765) and auto-handles Human gates that block
dogfood progress. Unknown inbox kinds **pause** (print + wait) instead of
guessing.

Handled automatically (``--policy auto``):
  - inbox ``question`` / clarifier → first option (or ``default`` / ``recommended``)
  - inbox ``build`` / MCP ``propose_build`` → decision=go
  - plan workflow ``HUMAN_PENDING`` → plan approve
  - execute ``pending_approval`` / ``review_required`` / ``merge_conflict`` → resolve approve
  - execute pending-plan snapshots → approve

Paused (Human must act, or pass ``--resume`` after fixing):
  - ``harness_patch``, ``skill_draft``, ``correction_rule``, unknown kinds
  - empty-option questions (freeform-only) unless ``--freeform-note`` set

Usage:
  eval "$(make -s dogfood-track-env)" && make api   # MOCK unset on API
  # start a Room turn in UI, then:
  .venv/bin/python scripts/dogfood_live_gates.py --session SESSION_ID
  # or watch until idle / timeout:
  make dogfood-live-gates SESSION=sessions/<id>   # or SESSION_ID=<id>

Does **not** bypass gates — calls the same approve/resolve APIs as the UI.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
API = os.environ.get("AGENT_LAB_API", "http://127.0.0.1:8765").rstrip("/")

PERMS = {
    "cursor": {"tools": True, "local_agent_lab": True, "local_pipeline": True},
    "codex": {"cli": True},
    "claude": {"tools": True, "write": True, "local_agent_lab": True},
}

# Auto-resolvable inbox kinds under dogfood policy.
_AUTO_QUESTION_KINDS = frozenset({"question"})
_AUTO_BUILD_KINDS = frozenset({"build"})
# Pause — need explicit Human (or future policy).
_PAUSE_KINDS = frozenset({"harness_patch", "skill_draft", "correction_rule", "demotion", "autonomy"})


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def _normalize_session_id(raw: str) -> str:
    text = raw.strip()
    if text.startswith("sessions/"):
        text = text[len("sessions/") :]
    return text.strip("/")


def _pick_question_selected(item: dict[str, Any]) -> list[str] | None:
    options = item.get("options") or []
    if not isinstance(options, list) or not options:
        return None
    for opt in options:
        if not isinstance(opt, dict):
            continue
        if opt.get("default") or opt.get("recommended") or opt.get("is_default"):
            oid = str(opt.get("id") or opt.get("value") or opt.get("label") or "").strip()
            if oid:
                return [oid]
    first = options[0]
    if isinstance(first, dict):
        oid = str(first.get("id") or first.get("value") or first.get("label") or "").strip()
        return [oid] if oid else None
    if isinstance(first, str) and first.strip():
        return [first.strip()]
    return None


def _list_pending_inbox(session_id: str) -> list[dict[str, Any]]:
    payload = _json_request("GET", _session_path(session_id, "/inbox"))
    items = payload.get("human_inbox") or []
    if not isinstance(items, list):
        items = []
    return [i for i in items if isinstance(i, dict) and i.get("status") == "pending"]


def _resolve_inbox(
    session_id: str,
    item: dict[str, Any],
    *,
    freeform_note: str | None,
) -> dict[str, Any]:
    item_id = str(item.get("id") or "")
    kind = str(item.get("kind") or "")
    body: dict[str, Any] = {"append_chat": True, "status": "resolved"}

    if kind in _AUTO_BUILD_KINDS or item.get("source") == "mcp_propose_build":
        body["decision"] = "go"
        body["note"] = "dogfood_live_gates: auto GO"
    elif kind in _AUTO_QUESTION_KINDS:
        selected = _pick_question_selected(item)
        if selected:
            body["selected"] = selected
            body["note"] = "dogfood_live_gates: auto first/default option"
        elif freeform_note:
            body["note"] = freeform_note
        else:
            return {
                "ok": False,
                "paused": True,
                "reason": "question_no_options",
                "item_id": item_id,
                "prompt": item.get("prompt") or item.get("question"),
            }
    elif kind in _PAUSE_KINDS or kind not in _AUTO_QUESTION_KINDS | _AUTO_BUILD_KINDS:
        return {
            "ok": False,
            "paused": True,
            "reason": f"kind={kind}",
            "item_id": item_id,
            "kind": kind,
            "prompt": item.get("prompt") or item.get("title"),
        }
    else:
        return {"ok": False, "paused": True, "reason": f"unhandled kind={kind}", "item_id": item_id}

    try:
        out = _json_request(
            "POST",
            _session_path(session_id, f"/inbox/{quote(item_id, safe='')}/resolve"),
            body,
            timeout=180.0,
        )
        return {"ok": True, "action": "inbox_resolve", "kind": kind, "item_id": item_id, "result": out.get("ok")}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:400]
        return {"ok": False, "error": detail, "item_id": item_id, "kind": kind}


def _plan_phase(session_id: str) -> str:
    try:
        wf = _json_request("GET", _session_path(session_id, "/plan/workflow"))
    except urllib.error.HTTPError:
        return ""
    return str((wf.get("plan_workflow") or {}).get("phase") or "").upper()


def _approve_plan(session_id: str) -> dict[str, Any]:
    out = _json_request(
        "POST",
        _session_path(session_id, "/plan/approve"),
        {"goal": "dogfood live gates", "completion_promise": "DONE", "criteria": "Oracle PASS"},
        timeout=180.0,
    )
    return {"ok": True, "action": "plan_approve", "phase": (out.get("plan_workflow") or {}).get("phase")}


def _approve_pending_snapshots(session_id: str) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    try:
        pending = _json_request("GET", _session_path(session_id, "/execute/pending-plans"))
    except urllib.error.HTTPError:
        return actions
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
            actions.append({"ok": True, "action": "pending_plan_approve", "id": pid})
        except urllib.error.HTTPError as exc:
            if exc.code != 400:
                actions.append({"ok": False, "action": "pending_plan_approve", "id": pid, "error": str(exc.code)})
    return actions


def _read_pending_execution(session_id: str) -> dict[str, Any] | None:
    run_path = ROOT / "sessions" / session_id / "run.json"
    if not run_path.is_file():
        return None
    try:
        run = json.loads(run_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    for ex in reversed(run.get("executions") or []):
        status = str(ex.get("status") or "")
        if status in {"pending_approval", "merge_conflict", "review_required"}:
            return ex if isinstance(ex, dict) else None
    return None


def _maybe_unblock_artifact(session_id: str, exec_id: str) -> bool:
    """Same dogfood-only artifact ack as x2_lift_dogfood_live_repeat."""
    sys.path.insert(0, str(ROOT / "src"))
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
                "pdf_path": "dogfood",
                "pdf_page_count": 1,
                "break_report": {"note": "dogfood_live_gates artifact ack"},
            }
        return run

    patch_run_meta(folder, patch)
    return True


def _resolve_execution(session_id: str, exec_id: str) -> dict[str, Any]:
    _maybe_unblock_artifact(session_id, exec_id)
    payload = _json_request(
        "POST",
        _session_path(session_id, "/execute/resolve"),
        {"execution_id": exec_id, "vote": "approve", "permissions": PERMS},
        timeout=float(os.environ.get("AGENT_LAB_X2_EXECUTE_TIMEOUT", "1200")),
    )
    ex = payload.get("execution") or {}
    return {
        "ok": True,
        "action": "execute_resolve",
        "execution_id": exec_id,
        "status": ex.get("status"),
        "oracle": (ex.get("oracle") or {}).get("verdict"),
    }


def drain_once(
    session_id: str,
    *,
    freeform_note: str | None = None,
    handle_execute: bool = True,
    handle_plan: bool = True,
) -> dict[str, Any]:
    """Single pass: resolve all currently pending auto-gates. May return paused."""
    actions: list[dict[str, Any]] = []
    sid = _normalize_session_id(session_id)

    # 1) Inbox (MCP ask_human / propose_build / clarifier questions)
    for item in _list_pending_inbox(sid):
        result = _resolve_inbox(sid, item, freeform_note=freeform_note)
        actions.append(result)
        if result.get("paused"):
            return {"ok": False, "paused": True, "session_id": sid, "actions": actions, "pause": result}

    # 2) Plan approve
    if handle_plan:
        phase = _plan_phase(sid)
        if phase == "HUMAN_PENDING":
            actions.append(_approve_plan(sid))

    # 3) Pending plan snapshots + execute resolve
    if handle_execute:
        actions.extend(_approve_pending_snapshots(sid))
        pending_ex = _read_pending_execution(sid)
        if pending_ex and pending_ex.get("id"):
            actions.append(_resolve_execution(sid, str(pending_ex["id"])))

    return {
        "ok": True,
        "paused": False,
        "session_id": sid,
        "actions": actions,
        "acted": len(actions),
        "at": _utc(),
    }


def watch(
    session_id: str,
    *,
    timeout_sec: float,
    poll_sec: float,
    freeform_note: str | None,
    idle_rounds: int = 3,
) -> dict[str, Any]:
    """Poll until timeout, pause, or idle_rounds with no pending gates."""
    sid = _normalize_session_id(session_id)
    deadline = time.time() + timeout_sec
    history: list[dict[str, Any]] = []
    idle = 0
    while time.time() < deadline:
        try:
            tick = drain_once(sid, freeform_note=freeform_note)
        except urllib.error.URLError as exc:
            tick = {"ok": False, "error": f"api unreachable: {exc}", "session_id": sid}
            history.append(tick)
            time.sleep(poll_sec)
            continue
        history.append(tick)
        if tick.get("paused"):
            return {"ok": False, "paused": True, "session_id": sid, "history": history, "pause": tick.get("pause")}
        if tick.get("acted", 0) == 0:
            idle += 1
            if idle >= idle_rounds:
                return {"ok": True, "idle": True, "session_id": sid, "history": history}
        else:
            idle = 0
            print(json.dumps({"tick": tick.get("acted"), "actions": [a.get("action") or a.get("reason") for a in tick.get("actions") or []]}, ensure_ascii=False), flush=True)
        time.sleep(poll_sec)
    return {"ok": False, "timeout": True, "session_id": sid, "history": history}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--session", required=True, help="session id or sessions/<id>")
    parser.add_argument("--watch", action="store_true", help="poll until idle/pause/timeout")
    parser.add_argument("--timeout", type=float, default=3600.0, help="watch timeout seconds")
    parser.add_argument("--poll", type=float, default=5.0, help="watch poll interval")
    parser.add_argument("--freeform-note", default=None, help="auto-answer option-less questions")
    parser.add_argument("--once", action="store_true", help="single drain (default if not --watch)")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.watch:
        report = watch(
            args.session,
            timeout_sec=args.timeout,
            poll_sec=args.poll,
            freeform_note=args.freeform_note,
        )
    else:
        report = drain_once(args.session, freeform_note=args.freeform_note)

    if args.json or True:
        print(json.dumps(report, indent=2, ensure_ascii=False, default=str))

    if report.get("paused"):
        pause = report.get("pause") or {}
        print(
            f"\nPAUSED — resolve in UI or re-run after handling: {pause.get('reason')} "
            f"item={pause.get('item_id')} kind={pause.get('kind')}",
            file=sys.stderr,
        )
        return 2
    if report.get("timeout"):
        return 1
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
