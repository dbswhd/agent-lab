"""Plan peer-review ITERATE loop — ralplan-style verdict parsing (P1-b)."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Literal

PlanPeerVerdict = Literal["iterate", "accept", "reject", "unknown"]

_ITERATE_RE = re.compile(r"\b(?:ITERATE|REJECT|REVISION\s+NEEDED)\b", re.I)
_ACCEPT_RE = re.compile(r"\bact:\s*ENDORSE\b", re.I)
_CHALLENGE_RE = re.compile(r"\bact:\s*CHALLENGE\b", re.I)
_BLOCK_RE = re.compile(r"\bact:\s*BLOCK\b", re.I)


def _message_text(message: Any) -> str:
    if message is None:
        return ""
    if isinstance(message, dict):
        return str(message.get("content") or message.get("text") or "")
    return str(getattr(message, "content", "") or "")


def parse_plan_peer_verdict(replies: list[Any]) -> PlanPeerVerdict:
    """Map peer-review replies to ralplan-style iterate / accept / reject."""
    if not replies:
        return "unknown"
    combined = "\n".join(_message_text(m) for m in replies)
    upper = combined.upper()
    if _BLOCK_RE.search(combined):
        return "reject"
    if _CHALLENGE_RE.search(combined) or _ITERATE_RE.search(combined):
        return "iterate"
    if _ACCEPT_RE.search(combined) and not _CHALLENGE_RE.search(combined):
        return "accept"
    if "ENDORSE" in upper and "CHALLENGE" not in upper:
        return "accept"
    return "unknown"


def finalize_plan_peer_review_round(
    folder: Path,
    *,
    run_meta: dict[str, Any] | None,
    replies: list[Any],
    human_turn: int = 0,
) -> PlanPeerVerdict:
    """Harvest plan objections + persist ``last_peer_verdict`` on run.json."""
    from agent_lab.run.meta import patch_run_meta as _patch

    if run_meta is not None and replies:
        from agent_lab.room.objections import harvest_objections_from_turn

        harvest_objections_from_turn(
            run_meta,
            replies,
            human_turn=human_turn,
            mode="plan",
        )

    verdict = parse_plan_peer_verdict(replies)

    def _stamp(run: dict[str, Any]) -> dict[str, Any]:
        from agent_lab.plan.workflow import get_plan_workflow

        pw = get_plan_workflow(run)
        pw["last_peer_verdict"] = verdict
        run["plan_workflow"] = pw
        if run_meta is not None and run_meta.get("objections") is not None:
            run["objections"] = run_meta.get("objections")
        return run

    _patch(folder, _stamp)
    return verdict
