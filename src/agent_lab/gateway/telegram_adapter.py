"""Telegram two-way adapter — Gateway Phase D MVP."""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from agent_lab.gateway.config import load_gateway_config
from agent_lab.gateway.router import route_inbound
from agent_lab.gate_scope import public_gate_scope_payload, set_gate_profile
from agent_lab.human_inbox import (
    find_inbox_item,
    pending_inbox_items,
    public_inbox_payload,
    resolve_inbox_item,
)
from agent_lab.plan_workflow import approve_plan, get_plan_workflow, plan_workflow_phase
from agent_lab.run_meta import read_run_meta

_log = logging.getLogger(__name__)


def _telegram_cfg() -> dict[str, Any]:
    return dict(load_gateway_config().get("telegram") or {})


def is_chat_allowed(chat_id: int | str | None) -> bool:
    if chat_id is None:
        return False
    cfg = _telegram_cfg()
    if not cfg.get("enabled"):
        return False
    allowed = cfg.get("allowed_chat_ids") or []
    if not allowed:
        return True
    try:
        cid = int(chat_id)
    except (TypeError, ValueError):
        return False
    return cid in allowed


def send_telegram_message(
    chat_id: int | str,
    text: str,
    *,
    reply_markup: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = _telegram_cfg()
    token = str(cfg.get("bot_token") or "").strip()
    if not token:
        return {"ok": False, "reason": "bot_token_missing"}
    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "text": text[:4096],
        "disable_web_page_preview": True,
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("utf-8")
            data = json.loads(raw) if raw else {}
            return {"ok": bool(data.get("ok")), "result": data.get("result"), "raw": data}
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        _log.warning("telegram send failed: %s", exc)
        return {"ok": False, "error": str(exc)}


def _session_folder(session_id: str) -> Path | None:
    from agent_lab.session import SESSIONS_DIR

    folder = SESSIONS_DIR / session_id
    return folder if folder.is_dir() else None


def _ensure_session_gate_profile(folder: Path, gate_profile: str) -> None:
    if gate_profile in ("dev", "assistant"):
        set_gate_profile(folder, gate_profile)  # type: ignore[arg-type]


def handle_gateway_command(
    *,
    session_id: str,
    text: str,
    gate_profile: str = "assistant",
) -> dict[str, Any]:
    """Parse routed text into inbox resolve / plan approve / status."""
    folder = _session_folder(session_id)
    if folder is None:
        return {"ok": False, "reason": "session_not_found", "session_id": session_id}

    _ensure_session_gate_profile(folder, gate_profile)
    cmd = (text or "").strip()
    lower = cmd.lower()

    if not cmd or lower in ("/status", "status", "/help", "help"):
        run = read_run_meta(folder)
        pw = get_plan_workflow(run)
        inbox = public_inbox_payload(run)
        gates = public_gate_scope_payload(run)
        pending = pending_inbox_items(run)
        lines = [
            f"session: {session_id}",
            f"gate_profile: {gates.get('gate_profile')}",
            f"plan_workflow: {pw.get('phase') or 'off'}",
            f"inbox_pending: {inbox.get('pending_count', 0)}",
        ]
        for item in pending[:5]:
            lines.append(f"  - {item.get('id')}: {item.get('kind')} {str(item.get('prompt') or '')[:80]}")
        lines.append("Commands: /status | /approve plan | /approve merge | /approve auto | /approve skill")
        return {"ok": True, "reply": "\n".join(lines)}

    if lower.startswith("/approve plan") or lower == "approve plan":
        try:
            result = approve_plan(folder)
        except ValueError as exc:
            return {"ok": False, "reply": f"plan approve failed: {exc}"}
        phase = (result.get("plan_workflow") or {}).get("phase")
        return {"ok": True, "reply": f"plan approved → {phase}", "result": result}

    if lower.startswith("/approve merge") or lower == "approve merge":
        from agent_lab.plan_execute import confirm_merge_execution, resolve_execution
        from agent_lab.runtime.snapshot import pending_execution

        run = read_run_meta(folder)
        pending = pending_execution(run)
        if not pending or not pending.get("id"):
            return {"ok": False, "reply": "no pending execution to merge"}
        execution_id = str(pending.get("id"))
        status = str(pending.get("status") or "")
        merge_status = str((pending.get("merge") or {}).get("status") or "")
        try:
            if status == "merge_conflict" or merge_status == "conflict":
                result = confirm_merge_execution(folder, execution_id=execution_id)
                reply = f"merge confirmed ({execution_id})"
            else:
                result = resolve_execution(
                    folder,
                    execution_id=execution_id,
                    vote="approve",
                    approved_by="human",
                )
                merged = result.get("execution") or {}
                reply = f"merge approved ({execution_id}) → {merged.get('status') or 'ok'}"
        except ValueError as exc:
            return {"ok": False, "reply": f"merge confirm failed: {exc}"}
        except Exception as exc:
            return {"ok": False, "reply": f"merge confirm error: {exc}"}
        return {"ok": True, "reply": reply, "result": result}

    if lower.startswith("/approve auto") or lower == "approve auto":
        from agent_lab.auto_merge import evaluate_auto_merge_eligibility, resolve_auto_merge
        from agent_lab.runtime.snapshot import pending_execution

        run = read_run_meta(folder)
        pending = pending_execution(run)
        if not pending or not pending.get("id"):
            return {"ok": False, "reply": "no pending execution to auto-merge"}
        execution_id = str(pending.get("id"))
        elig = evaluate_auto_merge_eligibility(folder, execution_id=execution_id)
        if not elig.get("eligible"):
            reason = elig.get("reason") or "not eligible"
            return {"ok": False, "reply": f"auto-merge blocked: {reason}", "eligibility": elig}
        try:
            result = resolve_auto_merge(folder, execution_id=execution_id)
        except ValueError as exc:
            return {"ok": False, "reply": f"auto-merge failed: {exc}"}
        except Exception as exc:
            return {"ok": False, "reply": f"auto-merge error: {exc}"}
        auto = result.get("auto_merge") or {}
        return {
            "ok": True,
            "reply": (
                f"auto-merge ok ({execution_id}) "
                f"classifier={auto.get('classifier')} "
                f"budget {auto.get('budget_before')}→{auto.get('budget_after')}"
            ),
            "result": result,
        }

    if lower.startswith("/approve skill") or lower == "approve skill":
        run = read_run_meta(folder)
        pending_skills = [item for item in pending_inbox_items(run) if item.get("kind") == "skill_draft"]
        if not pending_skills:
            return {"ok": False, "reply": "no pending skill draft to promote"}
        item = pending_skills[-1]
        refs = list(item.get("refs") or [])
        draft_id = refs[0] if refs else None
        if not draft_id:
            return {"ok": False, "reply": "skill draft missing id"}
        try:
            resolve_inbox_item(
                folder,
                str(item.get("id")),
                status="resolved",
                selected=["approve"],
                append_chat=False,
            )
        except ValueError as exc:
            return {"ok": False, "reply": f"skill promote failed: {exc}"}
        return {
            "ok": True,
            "reply": f"skill promoted ({draft_id})",
        }

    if lower.startswith("/resolve ") or lower.startswith("resolve "):
        parts = cmd.split(maxsplit=2)
        if len(parts) < 3:
            return {
                "ok": False,
                "reply": "usage: /resolve <inbox_id> <answer|go|defer|reject>",
            }
        item_id = parts[1].strip()
        answer = parts[2].strip()
        run = read_run_meta(folder)
        item = find_inbox_item(run, item_id)
        if item is None:
            return {"ok": False, "reply": f"inbox item not found: {item_id}"}
        kind = item.get("kind")
        try:
            if kind == "build":
                decision = answer.lower()
                if decision not in ("go", "defer", "reject"):
                    return {"ok": False, "reply": "build resolve: go|defer|reject"}
                resolve_inbox_item(folder, item_id, status="resolved", decision=decision)
            else:
                resolve_inbox_item(
                    folder,
                    item_id,
                    status="resolved",
                    selected=[answer],
                    note=answer,
                )
        except ValueError as exc:
            return {"ok": False, "reply": str(exc)}
        return {"ok": True, "reply": f"resolved {item_id}"}

    if plan_workflow_phase(read_run_meta(folder)).upper() == "HUMAN_PENDING":
        return {
            "ok": False,
            "reply": "plan awaiting approval — send `/approve plan`",
        }

    pending = pending_inbox_items(read_run_meta(folder))
    if pending:
        head = pending[0]
        return {
            "ok": False,
            "reply": (f"pending inbox {head.get('id')} ({head.get('kind')}) — `/resolve {head.get('id')} <answer>`"),
        }

    return {"ok": True, "reply": f"no action for: {cmd[:120]}"}


def process_telegram_update(update: dict[str, Any]) -> dict[str, Any]:
    message = update.get("message") or update.get("edited_message") or {}
    if not message:
        return {"ok": True, "skipped": True, "reason": "no_message"}
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    if not is_chat_allowed(chat_id):
        return {"ok": False, "reason": "chat_not_allowed", "chat_id": chat_id}

    text = str(message.get("text") or "").strip()
    routed = route_inbound(channel="telegram", text=text, chat_id=chat_id)
    result = handle_gateway_command(
        session_id=routed["session_id"],
        text=routed.get("text") or text,
        gate_profile=str(routed.get("gate_profile") or "assistant"),
    )
    reply = str(result.get("reply") or "")
    if reply and chat_id is not None:
        send_telegram_message(chat_id, reply)
    result["route"] = routed
    return result


def notify_inbox_pending(
    session_id: str,
    item: dict[str, Any],
    *,
    chat_ids: list[int] | None = None,
) -> dict[str, Any]:
    """Push pending inbox item to Telegram allowed chats."""
    cfg = _telegram_cfg()
    if not cfg.get("enabled"):
        return {"ok": True, "skipped": True, "reason": "telegram_disabled"}
    targets = chat_ids or list(cfg.get("allowed_chat_ids") or [])
    if not targets:
        return {"ok": True, "skipped": True, "reason": "no_chat_ids"}
    prompt = str(item.get("prompt") or item.get("summary") or item.get("id") or "Inbox")
    kind = item.get("kind") or "item"
    item_id = item.get("id") or ""
    text = f"[{session_id}] inbox {kind}\n{prompt[:500]}\n\n`/resolve {item_id} <answer>` or `/approve plan`"
    results = [send_telegram_message(cid, text) for cid in targets]
    return {"ok": all(r.get("ok") for r in results), "results": results}


def _notify_telegram_text(text: str, *, chat_ids: list[int] | None = None) -> dict[str, Any]:
    cfg = _telegram_cfg()
    if not cfg.get("enabled"):
        return {"ok": True, "skipped": True, "reason": "telegram_disabled"}
    targets = chat_ids or list(cfg.get("allowed_chat_ids") or [])
    if not targets:
        return {"ok": True, "skipped": True, "reason": "no_chat_ids"}
    results = [send_telegram_message(cid, text) for cid in targets]
    return {"ok": all(r.get("ok") for r in results), "results": results}


def notify_merge_ready(payload: dict[str, Any]) -> dict[str, Any]:
    session_id = str(payload.get("session_id") or "")
    exec_id = str(payload.get("execution_id") or "")
    profile = str(payload.get("gate_profile") or "")
    eligibility = (
        payload.get("auto_merge_eligibility") if isinstance(payload.get("auto_merge_eligibility"), dict) else {}
    )
    auto_hint = ""
    if eligibility.get("eligible"):
        auto_hint = "\n`/approve auto` or `/approve merge`"
    elif profile == "assistant":
        auto_hint = "\n`/approve merge`"
    text = f"[{session_id}] merge ready\nexecution `{exec_id}` (profile: {profile}){auto_hint}"
    return _notify_telegram_text(text)


def notify_gate_blocked(payload: dict[str, Any]) -> dict[str, Any]:
    session_id = str(payload.get("session_id") or "")
    reason = str(payload.get("block_reason") or payload.get("block_source") or "blocked")
    next_action = str(payload.get("next_allowed_action") or "")
    suffix = f"\nNext: {next_action}" if next_action else ""
    text = f"[{session_id}] gate blocked\n{reason[:500]}{suffix}"
    return _notify_telegram_text(text)


def notify_schedule_tick(payload: dict[str, Any]) -> dict[str, Any]:
    session_id = str(payload.get("session_id") or "")
    schedule_id = str(payload.get("schedule_id") or "")
    template_id = str(payload.get("template_id") or "")
    tpl = f" template={template_id}" if template_id else ""
    text = f"[{session_id}] schedule tick `{schedule_id}`{tpl}"
    return _notify_telegram_text(text)


def notify_auto_merge_blocked(payload: dict[str, Any]) -> dict[str, Any]:
    session_id = str(payload.get("session_id") or "")
    exec_id = str(payload.get("execution_id") or "")
    profile = str(payload.get("gate_profile") or "")
    reason = str(payload.get("reason") or "auto_merge_not_eligible")
    source = str(payload.get("source") or "")
    src = f" ({source})" if source else ""
    text = (
        f"[{session_id}] auto-merge blocked{src}\n"
        f"execution `{exec_id}` (profile: {profile})\n"
        f"reason: {reason[:240]}\n"
        f"`/approve merge`"
    )
    return _notify_telegram_text(text)
