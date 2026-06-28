"""Agent-to-agent mailbox in run.json (mailbox lite — no separate processes)."""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any

RUN_MAILBOX_KEY = "mailbox"
_AGENT_IDS = frozenset({"cursor", "codex", "claude"})
_AT_AGENT_RE = re.compile(r"^@?(cursor|codex|claude)$", re.I)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_mail_id() -> str:
    return f"mb-{uuid.uuid4().hex[:10]}"


def normalize_mailbox_message(raw: dict[str, Any]) -> dict[str, Any]:
    mid = str(raw.get("id") or _new_mail_id()).strip() or _new_mail_id()
    to_agent = str(raw.get("to") or "").strip().lower()
    from_agent = str(raw.get("from") or "").strip().lower()
    body = str(raw.get("body") or "").strip()[:4000]
    out: dict[str, Any] = {
        "id": mid,
        "from": from_agent,
        "to": to_agent,
        "body": body,
        "ts": str(raw.get("ts") or _now()),
        "read": bool(raw.get("read")),
    }
    if raw.get("task_id"):
        out["task_id"] = str(raw["task_id"]).strip()[:80]
    if raw.get("human_turn") is not None:
        try:
            out["human_turn"] = int(raw["human_turn"])
        except (TypeError, ValueError):
            pass
    if raw.get("parallel_round") is not None:
        try:
            out["parallel_round"] = int(raw["parallel_round"])
        except (TypeError, ValueError):
            pass
    return out


def list_mailbox(run_meta: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not run_meta:
        return []
    raw = run_meta.get(RUN_MAILBOX_KEY)
    if not isinstance(raw, list):
        return []
    return [normalize_mailbox_message(m) for m in raw if isinstance(m, dict)]


def write_mailbox(run_meta: dict[str, Any], messages: list[dict[str, Any]]) -> None:
    run_meta[RUN_MAILBOX_KEY] = [normalize_mailbox_message(m) for m in messages]


def _parse_to_agent(envelope: dict[str, Any], refs: list[str], body: str) -> str | None:
    to_raw = envelope.get("to")
    if to_raw:
        to_l = str(to_raw).strip().lower()
        if to_l in _AGENT_IDS:
            return to_l
    for ref in refs:
        m = _AT_AGENT_RE.match(str(ref).strip())
        if m:
            return m.group(1).lower()
    return None


def append_mailbox_message(
    run_meta: dict[str, Any],
    *,
    from_agent: str,
    to_agent: str,
    body: str,
    task_id: str | None = None,
    human_turn: int | None = None,
    parallel_round: int | None = None,
) -> dict[str, Any] | None:
    from_a = str(from_agent or "").strip().lower()
    to_a = str(to_agent or "").strip().lower()
    text = (body or "").strip()
    if from_a not in _AGENT_IDS or to_a not in _AGENT_IDS or from_a == to_a or not text:
        return None
    msgs = list_mailbox(run_meta)
    for existing in msgs[-20:]:
        if (
            existing.get("from") == from_a
            and existing.get("to") == to_a
            and existing.get("body") == text
            and not existing.get("read")
        ):
            return existing
    msg = normalize_mailbox_message(
        {
            "from": from_a,
            "to": to_a,
            "body": text,
            "task_id": task_id,
            "human_turn": human_turn,
            "parallel_round": parallel_round,
            "read": False,
        }
    )
    msgs.append(msg)
    write_mailbox(run_meta, msgs)
    return msg


def harvest_mailbox_from_turn(
    run_meta: dict[str, Any],
    messages: list[Any],
    *,
    human_turn: int,
) -> list[dict[str, Any]]:
    """Parse agent-envelope act MESSAGE from the current human turn."""
    from agent_lab.agent.envelope import envelope_act, parse_agent_response

    last_user = -1
    for i, m in enumerate(messages):
        if getattr(m, "role", None) == "user":
            last_user = i
    turn = messages[last_user + 1 :] if last_user >= 0 else messages
    created: list[dict[str, Any]] = []
    for m in turn:
        if getattr(m, "role", None) != "agent":
            continue
        from_agent = str(getattr(m, "agent", "") or "").strip().lower()
        if from_agent not in _AGENT_IDS:
            continue
        env = getattr(m, "envelope", None)
        if env is not None and hasattr(env, "to_dict"):
            env = env.to_dict()
        if not isinstance(env, dict):
            parsed = parse_agent_response(getattr(m, "content", "") or "")
            env = parsed.envelope.to_dict() if parsed.envelope else None
        if not isinstance(env, dict):
            continue
        if envelope_act(env) != "MESSAGE":
            continue
        refs = [str(r) for r in (env.get("refs") or []) if str(r).strip()]
        to_agent = _parse_to_agent(env, refs, getattr(m, "content", "") or "")
        if not to_agent:
            continue
        body = str(env.get("message") or "").strip()
        if not body:
            parsed = parse_agent_response(getattr(m, "content", "") or "")
            body = (parsed.body or "").strip()
        task_id = None
        for ref in refs:
            if ref.startswith("t-") or ref.startswith("task:"):
                task_id = ref.replace("task:", "", 1).strip()
                break
        pr = getattr(m, "parallel_round", None)
        msg = append_mailbox_message(
            run_meta,
            from_agent=from_agent,
            to_agent=to_agent,
            body=body,
            task_id=task_id,
            human_turn=human_turn,
            parallel_round=int(pr) if pr is not None else None,
        )
        if msg:
            created.append(msg)
    return created


def unread_for_agent(run_meta: dict[str, Any] | None, agent: str) -> list[dict[str, Any]]:
    agent_l = str(agent or "").strip().lower()
    return [m for m in list_mailbox(run_meta) if m.get("to") == agent_l and not m.get("read")]


def mark_delivered(run_meta: dict[str, Any], agent: str, mail_ids: list[str]) -> None:
    if not mail_ids:
        return
    want = set(mail_ids)
    msgs = list_mailbox(run_meta)
    changed = False
    for m in msgs:
        if m.get("id") in want:
            m["read"] = True
            changed = True
    if changed:
        write_mailbox(run_meta, msgs)


def build_mailbox_block(run_meta: dict[str, Any] | None, agent: str) -> str:
    """Unread direct messages for this agent (marks delivered when rendered)."""
    unread = unread_for_agent(run_meta, agent)
    if not unread:
        return ""
    lines = ["[받은함 — 동료에게서]", ""]
    ids: list[str] = []
    for m in unread[-12:]:
        lines.append(f"- **{m.get('from')}** → 나: {str(m.get('body') or '')[:800]}")
        if m.get("task_id"):
            lines.append(f"  (task: {m.get('task_id')})")
        mid = m.get("id")
        if mid:
            ids.append(str(mid))
    lines.append("")
    lines.append("답장은 envelope `MESSAGE` + `to` 필드, 또는 본문에서 동료를 @멘션하세요.")
    if not run_meta:
        return ""
    mark_delivered(run_meta, agent, ids)
    return "\n".join(lines)


def mailbox_public_payload(run_meta: dict[str, Any] | None) -> dict[str, Any]:
    msgs = list_mailbox(run_meta)
    unread: dict[str, int] = {}
    for aid in _AGENT_IDS:
        unread[aid] = len(unread_for_agent(run_meta, aid))
    return {
        "mailbox": msgs[-50:],
        "mailbox_unread": unread,
    }
