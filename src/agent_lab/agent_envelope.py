"""Structured speech-act envelope for agent replies (Option B prototype)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Literal

from agent_lab.room_context import is_pass_response, is_pure_no_objection

ActType = Literal["PROPOSE", "AMEND", "ENDORSE", "CHALLENGE", "PASS", "BLOCK"]
ConsensusVerdict = Literal["endorse", "pass", "substantive", "neutral"]

VALID_ACTS: frozenset[str] = frozenset(
    {"PROPOSE", "AMEND", "ENDORSE", "CHALLENGE", "PASS", "BLOCK"}
)

# Acts where the human-readable body should stay very short (token efficiency).
COMPACT_ACTS: frozenset[str] = frozenset({"ENDORSE", "PASS"})

_ENVELOPE_FENCE = re.compile(
    r"^\s*```agent-envelope\s*\n(.*?)\n```\s*\n?",
    re.DOTALL | re.IGNORECASE,
)

# Mirror room_tasks._PROPOSED_RE — keep local to avoid import cycles.
_PROPOSED_RE = re.compile(r"\[PROPOSED:\s*([^\]]+)\]", re.I)


def body_has_proposed(text: str) -> bool:
    return bool(_PROPOSED_RE.search(text or ""))


@dataclass
class AgentEnvelope:
    act: ActType
    refs: list[str]
    confidence: float | None = None
    anchor_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"act": self.act, "refs": list(self.refs)}
        if self.confidence is not None:
            d["confidence"] = self.confidence
        if self.anchor_id:
            d["anchor_id"] = self.anchor_id
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgentEnvelope | None:
        act = str(data.get("act", "")).strip().upper()
        if act not in VALID_ACTS:
            return None
        refs_raw = data.get("refs") or []
        refs = [str(r).strip() for r in refs_raw if str(r).strip()]
        conf = data.get("confidence")
        confidence: float | None = None
        if conf is not None:
            try:
                confidence = float(conf)
            except (TypeError, ValueError):
                confidence = None
        anchor_id = data.get("anchor_id")
        return cls(
            act=act,  # type: ignore[arg-type]
            refs=refs,
            confidence=confidence,
            anchor_id=str(anchor_id).strip() if anchor_id else None,
        )


@dataclass
class ParsedAgentResponse:
    body: str
    envelope: AgentEnvelope | None
    raw: str
    envelope_parse_error: bool = False


def parse_envelope_dict(data: dict[str, Any] | None) -> AgentEnvelope | None:
    if not data or not isinstance(data, dict):
        return None
    return AgentEnvelope.from_dict(data)


def parse_agent_response(text: str) -> ParsedAgentResponse:
    """Split optional ```agent-envelope fence from human-readable body."""
    raw = text or ""
    m = _ENVELOPE_FENCE.match(raw)
    if not m:
        return ParsedAgentResponse(body=raw.strip(), envelope=None, raw=raw)
    try:
        payload = json.loads(m.group(1).strip())
    except json.JSONDecodeError:
        body = raw[m.end() :].strip()
        if not body:
            body = raw.strip()
        return ParsedAgentResponse(
            body=body,
            envelope=None,
            raw=raw,
            envelope_parse_error=True,
        )
    envelope = (
        AgentEnvelope.from_dict(payload)
        if isinstance(payload, dict)
        else None
    )
    body = raw[m.end() :].strip()
    if not body and envelope:
        body = raw.strip()
    return ParsedAgentResponse(body=body, envelope=envelope, raw=raw)


def envelope_act(envelope: dict[str, Any] | AgentEnvelope | None) -> ActType | None:
    if envelope is None:
        return None
    if isinstance(envelope, AgentEnvelope):
        return envelope.act
    act = str(envelope.get("act", "")).strip().upper()
    if act in VALID_ACTS:
        return act  # type: ignore[return-value]
    return None


def classify_consensus_reply(
    text: str,
    envelope: dict[str, Any] | AgentEnvelope | None = None,
) -> ConsensusVerdict:
    """Prefer envelope act; fall back to phrase heuristics."""
    if body_has_proposed(text):
        return "substantive"
    act = envelope_act(envelope)
    if act == "ENDORSE":
        return "endorse"
    if act == "PASS":
        return "pass"
    if act in ("AMEND", "PROPOSE", "CHALLENGE", "BLOCK"):
        return "substantive"
    if is_pure_no_objection(text):
        return "endorse"
    if is_pass_response(text):
        return "pass"
    body = (text or "").strip()
    if not body:
        return "neutral"
    if not is_pure_no_objection(text) and not is_pass_response(text):
        return "substantive"
    return "neutral"


def is_endorse_reply(
    text: str,
    envelope: dict[str, Any] | AgentEnvelope | None = None,
) -> bool:
    return classify_consensus_reply(text, envelope) == "endorse"


def is_pass_reply(
    text: str,
    envelope: dict[str, Any] | AgentEnvelope | None = None,
) -> bool:
    return classify_consensus_reply(text, envelope) == "pass"


def is_substantive_envelope_reply(
    text: str,
    envelope: dict[str, Any] | AgentEnvelope | None = None,
) -> bool:
    return classify_consensus_reply(text, envelope) == "substantive"


ENVELOPE_FORMAT_GUIDANCE = """\
[Speech-act envelope — consensus / review R2+]
Reply **must** start with this fenced JSON block, then your human-readable body:

```agent-envelope
{"act":"ENDORSE","refs":[],"confidence":0.9}
```

**Invalid — fence body must be JSON, not plain text (ignored by parser):**
```agent-envelope
TypeScript — one-line summary here
```

Acts (pick one):
- `PROPOSE` — new proposal or direction
- `AMEND` — agree with anchor but change scope/steps/risks (starts new anchor round)
- `ENDORSE` — full agreement with current anchor, **nothing** to add (never use with `[PROPOSED:]` or extra risks)
- `CHALLENGE` — disagree with reasoning
- `PASS` — nothing new vs peers (peer review)
- `BLOCK` — hard objection; must explain in body

`refs`: optional chat.jsonl line refs (e.g. `"L42"`). `confidence`: 0–1 optional.
The fence inner content must parse as **one JSON object** with an `"act"` field.
After the fence, write the normal readable reply for the Human.

**Efficiency (R2+):**
- `ENDORSE` / `PASS` → body **one line max** (e.g. `이의 없습니다` or `PASS`). Put reasoning in prior R1 if needed.
- `AMEND` / `PROPOSE` / `CHALLENGE` → lead with the delta; skip re-summarizing R1 peers.
- Always use the fence JSON so peers and turn_state can skip re-reading long prose.
"""


def envelope_protocol_block(*, context: str = "consensus") -> str:
    labels = {
        "consensus": "자유 토론 · 합의 확인 R2+",
        "review": "리뷰 · R2+ 순차",
        "discuss": "회의 · R2+ 순차 (동료 답변 반영)",
    }
    label = labels.get(context, context)
    return f"{ENVELOPE_FORMAT_GUIDANCE}\n(Context: {label})"
