"""Structured speech-act envelope for agent replies (Option B prototype)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Literal

from agent_lab.room.context import is_pass_response, is_pure_no_objection

ActType = Literal["PROPOSE", "AMEND", "ENDORSE", "CHALLENGE", "PASS", "BLOCK", "MESSAGE"]
ConsensusVerdict = Literal["endorse", "pass", "substantive", "neutral"]

VALID_ACTS: frozenset[str] = frozenset({"PROPOSE", "AMEND", "ENDORSE", "CHALLENGE", "PASS", "BLOCK", "MESSAGE"})

# Acts where the human-readable body should stay very short (token efficiency).
COMPACT_ACTS: frozenset[str] = frozenset({"ENDORSE", "PASS"})

_ENVELOPE_FENCE = re.compile(
    r"^\s*```agent-envelope\s*\n(.*?)\n```\s*\n?",
    re.DOTALL | re.IGNORECASE,
)

# Mirror room_tasks._PROPOSED_RE — keep local to avoid import cycles.
_PROPOSED_RE = re.compile(r"\[PROPOSED:\s*([^\]]+)\]", re.I)
# P5: 에이전트 직접 학습 기록 — [LEARNED: …] → learnings.md → wisdom index.
_LEARNED_RE = re.compile(r"\[LEARNED:\s*([^\]]+)\]", re.I)


def body_has_proposed(text: str) -> bool:
    return bool(_PROPOSED_RE.search(text or ""))


def extract_learned_notes(text: str) -> list[str]:
    """본문 ``[LEARNED: …]`` 마커 추출 (P5 stigmergy 쓰기 경로)."""
    return [m.group(1).strip() for m in _LEARNED_RE.finditer(text or "") if m.group(1).strip()]


@dataclass
class AgentEnvelope:
    act: ActType
    refs: list[str]
    confidence: float | None = None
    anchor_id: str | None = None
    to: str | None = None
    message: str | None = None
    dispatch: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"act": self.act, "refs": list(self.refs)}
        if self.confidence is not None:
            d["confidence"] = self.confidence
        if self.anchor_id:
            d["anchor_id"] = self.anchor_id
        if self.to:
            d["to"] = self.to
        if self.message:
            d["message"] = self.message
        if self.dispatch:
            d["dispatch"] = dict(self.dispatch)
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
        to_raw = data.get("to")
        msg_raw = data.get("message")
        dispatch_raw = data.get("dispatch")
        dispatch: dict[str, Any] | None = None
        if isinstance(dispatch_raw, dict) and dispatch_raw:
            dispatch = {str(k): v for k, v in dispatch_raw.items() if str(k).strip()}
        return cls(
            act=act,  # type: ignore[arg-type]
            refs=refs,
            confidence=confidence,
            anchor_id=str(anchor_id).strip() if anchor_id else None,
            to=str(to_raw).strip().lower() if to_raw else None,
            message=str(msg_raw).strip() if msg_raw else None,
            dispatch=dispatch,
        )


def envelope_dispatch(envelope: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(envelope, dict):
        return None
    raw = envelope.get("dispatch")
    if isinstance(raw, dict) and raw:
        return raw
    return None


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
    envelope = AgentEnvelope.from_dict(payload) if isinstance(payload, dict) else None
    body = raw[m.end() :].strip()
    if not body and envelope:
        body = raw.strip()
    return ParsedAgentResponse(body=body, envelope=envelope, raw=raw)


def parse_agent_response_v2(
    text: str,
    *,
    structured: dict[str, Any] | None = None,
) -> ParsedAgentResponse:
    """Prefer provider structured envelope JSON; fall back to fence-in-prose."""
    if structured and isinstance(structured, dict):
        envelope = AgentEnvelope.from_dict(structured)
        if envelope is not None:
            body = (text or "").strip()
            raw = text or json.dumps(structured, ensure_ascii=False)
            return ParsedAgentResponse(body=body, envelope=envelope, raw=raw)
    return parse_agent_response(text)


def split_structured_envelope_prefix(
    text: str,
) -> tuple[dict[str, Any] | None, str]:
    """Detect a leading JSON object with ``act`` (provider structured output)."""
    raw = text or ""
    if raw.lstrip().startswith("```"):
        return None, raw
    idx = raw.find("{")
    if idx < 0 or idx > 120:
        return None, raw
    chunk = raw[idx:]
    depth = 0
    for i, ch in enumerate(chunk):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    obj = json.loads(chunk[: i + 1])
                except json.JSONDecodeError:
                    return None, raw
                if isinstance(obj, dict) and str(obj.get("act") or "").strip():
                    rest = raw[idx + i + 1 :].lstrip()
                    return obj, rest
                return None, raw
    return None, raw


def envelope_act(envelope: dict[str, Any] | AgentEnvelope | None) -> ActType | None:
    if envelope is None:
        return None
    if isinstance(envelope, AgentEnvelope):
        return envelope.act
    act = str(envelope.get("act", "")).strip().upper()
    if act in VALID_ACTS:
        return act  # type: ignore[return-value]
    return None


# --- DECISION-FORK (M4) — ref-anchored options for Human Inbox ----------------

_FORK_FENCE = re.compile(
    r"```decision-fork\s*\n(.*?)\n```",
    re.DOTALL | re.IGNORECASE,
)


@dataclass(frozen=True)
class ForkOption:
    label: str
    refs: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {"label": self.label, "refs": list(self.refs)}


@dataclass(frozen=True)
class DecisionFork:
    """A structured Human-direction fork an agent raises (parallel to envelope acts)."""

    topic: str
    options: tuple[ForkOption, ...]

    def to_dict(self) -> dict[str, Any]:
        return {"topic": self.topic, "options": [o.to_dict() for o in self.options]}


def parse_decision_forks(text: str) -> list[DecisionFork]:
    """Parse ```decision-fork fenced JSON blocks. Pure, lenient, no LLM.

    Each block: ``{"topic": str, "options": [{"label": str, "refs": [str, ...]}]}``.
    Malformed JSON, missing topic, or empty options are skipped.
    """
    out: list[DecisionFork] = []
    for m in _FORK_FENCE.finditer(text or ""):
        try:
            data = json.loads(m.group(1).strip())
        except json.JSONDecodeError:
            continue
        if not isinstance(data, dict):
            continue
        topic = str(data.get("topic") or data.get("question") or "").strip()
        options: list[ForkOption] = []
        for raw in data.get("options") or []:
            if not isinstance(raw, dict):
                continue
            label = str(raw.get("label") or "").strip()
            if not label:
                continue
            refs = tuple(str(r).strip() for r in (raw.get("refs") or []) if str(r).strip())
            options.append(ForkOption(label=label[:120], refs=refs))
        if topic and options:
            out.append(DecisionFork(topic=topic[:200], options=tuple(options)))
    return out


def classify_consensus_reply(
    text: str,
    envelope: dict[str, Any] | AgentEnvelope | None = None,
) -> ConsensusVerdict:
    """Prefer envelope act; fall back to phrase heuristics when legacy enabled."""
    if body_has_proposed(text):
        return "substantive"
    act = envelope_act(envelope)
    if act == "ENDORSE":
        return "endorse"
    if act == "PASS":
        return "pass"
    if act in ("AMEND", "PROPOSE", "CHALLENGE", "BLOCK", "MESSAGE"):
        return "substantive"
    from agent_lab.reply_policy import legacy_endorse_enabled

    if not legacy_endorse_enabled():
        if is_pure_no_objection(text) or is_pass_response(text):
            return "neutral"
        body = (text or "").strip()
        return "neutral" if not body else "substantive"
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
- `MESSAGE` — direct note to one teammate (`"to":"codex"`, optional `"message"`; body can repeat). Not for Human.

`refs`: optional chat.jsonl line refs (e.g. `"L42"`) or task ids (`t-…`). `to`: cursor|codex|claude when `act` is MESSAGE. `confidence`: 0–1 optional.
The fence inner content must parse as **one JSON object** with an `"act"` field.
After the fence, write the normal readable reply for the Human.

**Efficiency (R2+):**
- `ENDORSE` / `PASS` → body **one line max** (e.g. `이의 없습니다` or `PASS`). Put reasoning in prior R1 if needed.
- `AMEND` / `PROPOSE` / `CHALLENGE` → lead with the delta; skip re-summarizing R1 peers.
- Always use the fence JSON so peers and turn_state can skip re-reading long prose.
"""

ENVELOPE_FORMAT_GUIDANCE_SHORT = """\
[Speech-act envelope — R2+]
Start with fenced JSON, then your readable body:

```agent-envelope
{"act":"ENDORSE","refs":[],"confidence":0.9}
```

Acts: PROPOSE | AMEND | ENDORSE | CHALLENGE | PASS | BLOCK | MESSAGE
ENDORSE/PASS → one-line body. Full rules: docs/HOOK-COMMUNICATE-REFORM.md
"""

DECISION_FORK_GUIDANCE_SHORT = """\
[DECISION-FORK — optional, after body]
```decision-fork
{"topic":"…","options":[{"label":"…","refs":["L42"]}]}
```
≥2 options, each with ≥1 ref.
"""

DECISION_FORK_GUIDANCE = """\
[DECISION-FORK — Human direction (optional, end of reply)]
When the **Human** must pick between concrete directions (not peer-only debate), add **one** fenced block **after** your readable body:

```decision-fork
{"topic":"short question for Human","options":[{"label":"Option A","refs":["L42"]},{"label":"Option B","refs":["L55"]}]}
```

Rules:
- **≥2 options**, each with **≥1 ref** (`chat.jsonl#Ln` as `L42`, or task id). Options without refs are **dropped** — do not invent.
- Use for real forks the Human must resolve; do not duplicate a plain `CHALLENGE` with no choices.
- Topic = one line question shown in Human Inbox.
"""


def envelope_protocol_block(*, context: str = "consensus", compact: bool = False) -> str:
    labels = {
        "consensus": "자유 토론 · 합의 확인 R2+",
        "review": "리뷰 · R2+ 순차",
        "discuss": "회의 · R2+ 순차 (동료 답변 반영)",
    }
    label = labels.get(context, context)
    if compact:
        return f"{ENVELOPE_FORMAT_GUIDANCE_SHORT}\n\n{DECISION_FORK_GUIDANCE_SHORT}\n(Context: {label})"
    return f"{ENVELOPE_FORMAT_GUIDANCE}\n\n{DECISION_FORK_GUIDANCE}\n(Context: {label})"
