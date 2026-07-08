"""Inbox Facilitator (M4) — DECISION-FORK options → Inbox question.

Ref-anchored, **no invent** (RFC §5.3 / §5.5):
- Deterministic by default (mock-safe): merge forks raised this turn, **drop any
  option without a ref**, dedupe by label, require ≥2 surviving options.
- A live Claude 1-call synthesizer is opt-in (``AGENT_LAB_FACILITATOR_LIVE`` or an
  injected ``facilitator_call``) for the prose→options case; its output must also
  be ``decision-fork`` blocks, so it flows through the **same** ref-drop merge and
  cannot invent a ref-less option either.

Mirrors ``adversarial_gate`` (injection / live flag / mock default).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from hashlib import sha1
from typing import Any

from agent_lab.agent.envelope import DecisionFork, parse_decision_forks
from agent_lab.env_flags import env_bool

_MAX_OPTIONS = 5
_MIN_OPTIONS = 2


@dataclass(frozen=True)
class FacilitatedQuestion:
    """One Inbox-ready question synthesized from forks — options anchored by refs."""

    prompt: str
    options: tuple[dict[str, Any], ...]
    refs: tuple[str, ...]
    harvest_key: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "prompt": self.prompt,
            "options": [dict(o) for o in self.options],
            "refs": list(self.refs),
            "harvest_key": self.harvest_key,
        }


def _option_id(label: str) -> str:
    return "o-" + sha1(label.strip().lower().encode("utf-8")).hexdigest()[:6]


def _topic_key(topic: str) -> str:
    return "fk-" + sha1(topic.strip().lower().encode("utf-8")).hexdigest()[:12]


def merge_forks(forks: list[DecisionFork]) -> list[FacilitatedQuestion]:
    """Deterministic merge — group by topic, drop ref-less options, dedupe by label."""
    by_topic: dict[str, list[DecisionFork]] = {}
    order: list[str] = []
    for fork in forks:
        key = fork.topic.strip().lower()
        if key not in by_topic:
            by_topic[key] = []
            order.append(key)
        by_topic[key].append(fork)

    out: list[FacilitatedQuestion] = []
    for key in order:
        group = by_topic[key]
        topic = group[0].topic
        seen_labels: set[str] = set()
        options: list[dict[str, Any]] = []
        refs_union: list[str] = []
        for fork in group:
            for opt in fork.options:
                if not opt.refs:  # no invent — an option must be anchored
                    continue
                label_key = opt.label.strip().lower()
                if label_key in seen_labels:
                    continue
                seen_labels.add(label_key)
                options.append({"id": _option_id(opt.label), "label": opt.label, "refs": list(opt.refs)})
                for ref in opt.refs:
                    if ref not in refs_union:
                        refs_union.append(ref)
        if len(options) < _MIN_OPTIONS:  # not a real fork once ref-less are dropped
            continue
        out.append(
            FacilitatedQuestion(
                prompt=topic,
                options=tuple(options[:_MAX_OPTIONS]),
                refs=tuple(refs_union),
                harvest_key=_topic_key(topic),
            )
        )
    return out


def _live_enabled() -> bool:
    return env_bool("AGENT_LAB_FACILITATOR_LIVE")


def _synthesis_prompt(prose_context: str) -> str:
    return (
        "다음 토론에서 Human이 방향을 정해야 할 갈림이 있으면, 각 선택지를 "
        "토론에 실제 등장한 근거(chat ref)에 anchored 시켜 정리하세요. "
        "근거 없는 선택지는 만들지 마세요. 갈림이 없으면 아무것도 출력하지 마세요.\n\n"
        "출력은 ```decision-fork 펜스 블록만:\n"
        '```decision-fork\n{"topic":"…","options":[{"label":"…","refs":["L42"]}]}\n```\n\n'
        f"토론:\n{prose_context.strip()}"
    )


def facilitate(
    forks: list[DecisionFork],
    *,
    prose_context: str = "",
    facilitator_call: Callable[[str], str] | None = None,
) -> list[FacilitatedQuestion]:
    """Forks → Inbox questions.

    Explicit forks are merged deterministically (no LLM). When there are no forks,
    an injected/live synthesizer may produce ``decision-fork`` blocks from prose;
    those are merged through the same ref-drop path. Mock default = no synthesis.
    """
    if forks:
        return merge_forks(forks)

    call = facilitator_call
    if call is None and _live_enabled():
        from agent_lab.claude import cli as claude_cli

        call = lambda prompt: claude_cli.invoke("inbox-facilitator", prompt, scribe=True)  # noqa: E731

    if call is None or not prose_context.strip():
        return []

    raw = call(_synthesis_prompt(prose_context))
    return merge_forks(parse_decision_forks(raw or ""))
