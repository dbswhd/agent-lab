"""N10a — correction harvester: user-turn corrections as Wisdom input.

Mirrors ``outcome_harvester.py`` (S1 RECORD) but observes the *human* side of a
turn instead of the agent side. A recurring correction (same pattern, distinct
sessions) is proposed to the user as a rule candidate via Human Inbox — never
applied automatically. See docs/N10-USER-LOOP-WISDOM-DRAFT.md (N10a).

Design constraints carried over from S1/S3 (NORTH-STAR §6 mote check):
- fail-open: any error is swallowed, never blocks a turn.
- no new 1st-class vocabulary: this is Wisdom's ``user_correction`` episode kind.
- no automatic edits to global config — promotion only appends to a repo-local
  markdown file after explicit Human Inbox approval.
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_lab.env_flags import env_bool
from agent_lab.run.meta import read_run_meta

# NOTE: agent_lab.outcome_harvester / agent_lab.feedback_advisor / agent_lab.human_inbox
# are imported lazily (function-local) throughout this module, not at module scope —
# this subsystem is a dense mutual-reference cluster (F12) and top-level imports here
# would create a real cycle (correction_harvester -> outcome_harvester -> human_inbox
# -> correction_harvester). Matches the existing convention in feedback_report.py /
# feedback_advisor.py / skill_drafts.py.

CORRECTION_PHASE = "user_correction"
_STATE_RELPATH = Path(".agent-lab") / "correction_rules_state.json"
_RULES_RELPATH = Path(".agent-lab") / "wisdom" / "correction_rules.md"

_STATE_LOCK = threading.Lock()


@dataclass(frozen=True, slots=True)
class CorrectionPattern:
    key: str
    label: str
    rule_text: str
    matcher: re.Pattern[str]


def correction_harvester_enabled() -> bool:
    return env_bool("AGENT_LAB_CORRECTION_HARVESTER", default=True)


# Deterministic, keyword-based — no LLM call (same S1.5 discipline as
# feedback_advisor's sha1-seeded explore decision: correction detection must
# be reproducible and cheap enough to run fail-open on every turn close).
_PATTERNS: tuple[CorrectionPattern, ...] = (
    CorrectionPattern(
        key="language_reminder",
        label="항상 한국어로 응답",
        rule_text="항상 한국어로 응답할 것. 코드/변수명은 영어 유지.",
        matcher=re.compile(r"한국어로|한글로|in korean|respond in korean", re.IGNORECASE),
    ),
    CorrectionPattern(
        key="redo_request",
        label="다시/제대로 요청",
        rule_text="이전 결과가 요구사항을 충족하지 못함 — 완료 기준을 더 명시적으로 재확인할 것.",
        matcher=re.compile(r"다시\s*(해|해줘|하자)|제대로\s*(해|안|좀)|처음부터\s*다시"),
    ),
    CorrectionPattern(
        key="negation_redirect",
        label="부정 정정",
        rule_text="사용자가 방향을 정정함 — 다음 지시 전 요구사항을 한 번 더 확인할 것.",
        matcher=re.compile(r"아니\s*(야|고|라|잖아)|그게\s*아니라|그거\s*아니고"),
    ),
    CorrectionPattern(
        key="retry_reflex",
        label="진단 없는 재시도",
        rule_text="실패 직후 재시도 전에 실패 원인을 먼저 한 줄로 설명할 것.",
        matcher=re.compile(r"^\s*(retry|재시도|다시\s*시도)\s*[.!]?\s*$", re.IGNORECASE),
    ),
)


def detect_user_correction(content: str) -> CorrectionPattern | None:
    text = (content or "").strip()
    if not text:
        return None
    for pattern in _PATTERNS:
        if pattern.matcher.search(text):
            return pattern
    return None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _topic_hash(topic: str) -> str:
    return "sha1:" + hashlib.sha1(topic.encode("utf-8")).hexdigest()[:16]


def _topic_text(folder: Path, run: dict[str, Any]) -> str:
    topic = str(run.get("topic") or "").strip()
    if topic:
        return topic
    topic_file = folder / "topic.txt"
    if topic_file.is_file():
        try:
            return topic_file.read_text(encoding="utf-8").strip()
        except OSError:
            return ""
    return ""


def _last_user_message(folder: Path) -> str:
    from agent_lab.session.chat_io import load_chat_dicts

    rows = load_chat_dicts(folder)
    for row in reversed(rows):
        if str(row.get("role") or "") == "user":
            return str(row.get("content") or "")
    return ""


def build_correction_record(folder: Path, topic: str, pattern: CorrectionPattern, excerpt: str) -> dict[str, Any]:
    from agent_lab.outcome_harvester import OUTCOME_LEDGER_SCHEMA_VERSION

    return {
        "v": OUTCOME_LEDGER_SCHEMA_VERSION,
        "ts": _now_iso(),
        "phase": CORRECTION_PHASE,
        "session_id": folder.name,
        "topic_hash": _topic_hash(topic),
        "pattern_key": pattern.key,
        "excerpt": excerpt[:120],
    }


def record_user_correction_outcome(folder: Path | None, human_turn: int) -> None:
    """Detect + RECORD a user correction for the turn that just closed (fail-open)."""
    if folder is None:
        return
    try:
        from agent_lab.outcome_harvester import append_outcome

        if not correction_harvester_enabled():
            return
        content = _last_user_message(folder)
        pattern = detect_user_correction(content)
        if pattern is None:
            return
        run = read_run_meta(folder)
        topic = _topic_text(folder, run)
        record = build_correction_record(folder, topic, pattern, content)
        append_outcome(record)
        maybe_propose_correction_rule(folder, pattern, root=None)
    except Exception:  # fail-open: correction harvest must never block a turn
        import logging

        logging.getLogger(__name__).warning("record_user_correction_outcome failed for %s", folder, exc_info=True)


# --- W2 pattern check + Human Inbox rule promotion ---------------------------


def _state_path(root: Path | None) -> Path:
    if root is None:
        from agent_lab.outcome_harvester import outcomes_path

        root = outcomes_path().parent.parent  # .agent-lab/outcomes.jsonl -> repo root
    return Path(root) / _STATE_RELPATH


def _load_state(root: Path | None) -> dict[str, Any]:
    path = _state_path(root)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _save_state(root: Path | None, state: dict[str, Any]) -> None:
    path = _state_path(root)
    with _STATE_LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _distinct_sessions_for_pattern(pattern_key: str, root: Path | None) -> set[str]:
    from agent_lab.outcome_harvester import outcomes_path

    path = outcomes_path(root)
    if not path.is_file():
        return set()
    sessions: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(row, dict):
            continue
        if row.get("phase") == CORRECTION_PHASE and row.get("pattern_key") == pattern_key:
            sid = str(row.get("session_id") or "")
            if sid:
                sessions.add(sid)
    return sessions


def maybe_propose_correction_rule(
    folder: Path, pattern: CorrectionPattern, *, root: Path | None
) -> dict[str, Any] | None:
    """Propose a rule candidate to Human Inbox once a pattern recurs across >= MIN_SAMPLE sessions."""
    from agent_lab.feedback_advisor import MIN_SAMPLE

    state = _load_state(root)
    raw_entry = state.get(pattern.key)
    entry: dict[str, Any] = raw_entry if isinstance(raw_entry, dict) else {}
    if entry.get("status") in ("proposed", "promoted", "rejected"):
        return None

    sessions = _distinct_sessions_for_pattern(pattern.key, root)
    if len(sessions) < MIN_SAMPLE:
        return None

    from agent_lab.human_inbox import create_inbox_item

    prompt = f'반복 교정 패턴 감지: "{pattern.label}" — {len(sessions)}개 세션에서 관측. 규칙으로 저장할까요?'
    inbox_item = create_inbox_item(
        folder,
        kind="correction_rule",
        source="correction_harvester",
        prompt=prompt,
        summary=pattern.rule_text,
        options=[
            {"id": "approve", "label": "규칙으로 저장"},
            {"id": "reject", "label": "무시"},
        ],
        refs=[pattern.key],
    )
    state[pattern.key] = {
        "status": "proposed",
        "inbox_id": inbox_item.get("id"),
        "session_count": len(sessions),
        "proposed_at": _now_iso(),
    }
    _save_state(root, state)
    return inbox_item


def _pattern_by_key(key: str) -> CorrectionPattern | None:
    for pattern in _PATTERNS:
        if pattern.key == key:
            return pattern
    return None


def promote_correction_rule(pattern_key: str, *, root: Path | None = None, session_count: int = 0) -> Path:
    """Append the approved rule to the repo-local Wisdom rules file (N10b SSOT seed).

    HS2-3/4 (fail-open): also writes/reinforces a playbook bullet — the ONLY
    playbook source today is a Human-Inbox-approved correction rule, so this
    call site doubles as both "correction_rules → playbook dual write" (HS2-3)
    and "Inbox approval → bullet" (HS2-4).
    """
    pattern = _pattern_by_key(pattern_key)
    rule_text = pattern.rule_text if pattern else pattern_key
    label = pattern.label if pattern else pattern_key
    dest = _rules_path(root)
    dest.parent.mkdir(parents=True, exist_ok=True)
    header = "# Correction Rules (N10a — Human-approved)\n\n"
    existing = dest.read_text(encoding="utf-8") if dest.is_file() else header
    entry = (
        f"## {label} (`{pattern_key}`)\n\n"
        f"{rule_text}\n\n"
        f"- 근거: {session_count}개 세션에서 반복 관측\n"
        f"- 승인일: {_now_iso()}\n\n"
    )
    dest.write_text(existing + entry, encoding="utf-8")
    _try_add_playbook_bullet(rule_text, pattern_key=pattern_key, root=root)
    return dest


def _try_add_playbook_bullet(rule_text: str, *, pattern_key: str, root: Path | None) -> None:
    try:
        from agent_lab.merge_gate import current_harness_rev
        from agent_lab.wisdom.playbook import add_bullet, playbook_enabled

        if not playbook_enabled():
            return
        path = None
        if root is not None:
            path = Path(root) / ".agent-lab" / "wisdom" / "playbook.jsonl"
        # HS5-6: stamp the harness revision active right now — if a later
        # harness_patch merge is rolled back, this bullet becomes quarantine-
        # eligible (merge_gate.rollback_harness_patch).
        add_bullet(
            rule_text,
            f"fp:user_correction:{pattern_key}",
            harness_rev=current_harness_rev(root),
            path=path,
        )
    except Exception:  # fail-open: playbook write must never block rule promotion
        import logging

        logging.getLogger(__name__).warning("playbook bullet write failed for %s", pattern_key, exc_info=True)


def _rules_path(root: Path | None) -> Path:
    if root is None:
        from agent_lab.outcome_harvester import outcomes_path

        root = outcomes_path().parent.parent
    return Path(root) / _RULES_RELPATH


def handle_correction_rule_inbox_resolve(
    folder: Path,
    item: dict[str, Any],
    *,
    selected: list[str] | None,
    status: str,
    root: Path | None = None,
) -> None:
    """Side-effect helper when inbox correction_rule item is resolved (mirrors skill_drafts)."""
    if item.get("kind") != "correction_rule":
        return
    refs = list(item.get("refs") or [])
    pattern_key = str(refs[0]) if refs else ""
    if not pattern_key:
        return

    state = _load_state(root)
    raw_entry = state.get(pattern_key)
    entry: dict[str, Any] = raw_entry if isinstance(raw_entry, dict) else {}

    if status in ("rejected", "superseded"):
        entry["status"] = "rejected"
        state[pattern_key] = entry
        _save_state(root, state)
        return

    choice = (selected or [""])[0].strip().lower()
    if choice == "approve":
        session_count = int(entry.get("session_count") or 0)
        promote_correction_rule(pattern_key, root=root, session_count=session_count)
        entry["status"] = "promoted"
        entry["promoted_at"] = _now_iso()
        state[pattern_key] = entry
        _save_state(root, state)

        from agent_lab.rule_sync import maybe_propose_rule_sync

        maybe_propose_rule_sync(folder, root=root)
    elif choice == "reject":
        entry["status"] = "rejected"
        state[pattern_key] = entry
        _save_state(root, state)


def public_correction_rules_payload(root: Path | None = None) -> dict[str, Any]:
    """Session-agnostic status snapshot (used by ops/report tooling, not gating)."""
    state = _load_state(root)
    return {"patterns": state, "enabled": correction_harvester_enabled()}


__all__ = [
    "CorrectionPattern",
    "correction_harvester_enabled",
    "detect_user_correction",
    "build_correction_record",
    "record_user_correction_outcome",
    "maybe_propose_correction_rule",
    "promote_correction_rule",
    "handle_correction_rule_inbox_resolve",
    "public_correction_rules_payload",
]
