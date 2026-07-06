"""Active roster helpers for agent payload / coordination text."""

from __future__ import annotations

from typing import Any

from agent_lab.run.state import RunStateLike

from agent_lab.provider_registry import get_provider

_KNOWN_AGENTS = ("cursor", "codex", "claude", "kimi_work")


def _label(agent: str) -> str:
    spec = get_provider(str(agent).strip().lower())
    return spec.label if spec else str(agent)


def active_agents_from_run_meta(run_meta: RunStateLike | None) -> list[str]:
    """Return lowercase agent ids for the current session turn roster."""
    if not run_meta:
        return []
    raw = run_meta.get("agents")
    if isinstance(raw, list):
        out = [str(a).strip().lower() for a in raw if str(a).strip()]
        if out:
            return out
    turns = run_meta.get("turns")
    if isinstance(turns, list) and turns:
        last = turns[-1]
        if isinstance(last, dict):
            agents = last.get("agents")
            if isinstance(agents, list):
                out = [str(a).strip().lower() for a in agents if str(a).strip()]
                if out:
                    return out
    return []


def inactive_known_agents(active: list[str]) -> list[str]:
    pool = {a.strip().lower() for a in active if str(a).strip()}
    return [a for a in _KNOWN_AGENTS if a not in pool]


def _capability_hint(agent: str) -> str:
    from agent_lab.room.agent_capabilities import DEFAULT_CAPABILITIES

    cap = DEFAULT_CAPABILITIES.get(agent, {})
    hint = str(cap.get("label") or "").strip()
    return f"{_label(agent)} ({hint})" if hint else _label(agent)


def build_active_roster_block(
    active: list[str],
    *,
    team_lead: str | None = None,
) -> str:
    """Constraints block: who is in this session vs off."""
    if not active:
        return ""
    lines = ["[Active roster — this session]"]
    lines.append(f"- **In room:** {', '.join(_capability_hint(a) for a in active)}")
    if team_lead and team_lead in active:
        lines.append(f"- **Turn lead:** {_label(team_lead)}")
    off = inactive_known_agents(active)
    if off:
        lines.append(f"- **Not in room (do not MESSAGE `to` these):** {', '.join(_label(a) for a in off)}")
    lines.append(
        "- Envelope `act: MESSAGE`, `to:` must name an **in-room** peer only. "
        "Do not address absent agents."
    )
    return "\n".join(lines)


def build_multi_agent_coordination(active: list[str]) -> str:
    names = ", ".join(_label(a) for a in active) if active else "peers in [Active roster]"
    off = inactive_known_agents(active)
    off_line = ""
    if off:
        off_line = (
            f"\n- Agents **not** in this session ({', '.join(_label(a) for a in off)}) "
            "are unavailable — do not delegate or MESSAGE them."
        )
    return f"""\
[Multi-agent coordination — {names}, one workspace]
- You **may** read/run/edit in this turn when it helps the debate move forward (Human granted full access).
- **Avoid collisions:** before editing a file a peer likely touched this turn, **Read** it first.
- **R1 (parallel):** prefer disjoint paths (analysis vs test vs patch in different files). If the same file is hot, **one editor per wave** — others review, verify, or `[PROPOSED:]` without overwriting.
- **R2+ (sequential):** you see peer outputs — **extend or fix**, do not blindly revert; state what you changed and why.
- Never silent-merge conflicting edits; flag conflict in `[PROPOSED:]` and let peers AMEND/ENDORSE — not a Human questionnaire.
- In-room peers may use tools when useful; coordinate only with agents listed in [Active roster].{off_line}
"""


def build_peer_decision_guidance(active: list[str]) -> str:
    names = ", ".join(_label(a) for a in active) if active else "in-room peers"
    return f"""\
[Peer decision — settle resolvable choices together]
- Resolve scope, approach, file choice, and verify order among {names} — state a **working assumption**, tag `[PROPOSED: …]`, and let peers ENDORSE / AMEND in the next round.
- Escalate to Human for: explicit approval gates (`GO`, budget, destructive prod), missing secrets/paths outside repo, a genuine fork, or unresolvable peer conflict after one amend round.
- Prefer **deciding together** on resolvable details over a low-value "Human에게 한 줄 확인".
"""


def delegator_persona(active: list[str]) -> str:
    if not active:
        return (
            "[Delegator · supervisor preset]\n"
            "Harness Supervisor seat: 턴 리드로 phase/GO를 제안하고, "
            "in-room peer에게 scoped review를 위임하세요. "
            "Human gate·fork·BLOCK은 Human에게만 올리세요. "
            '동료 위임 시 envelope `act: MESSAGE`, `to: <in-room agent>`를 사용하세요.'
        )
    peer_labels = ", ".join(_label(a) for a in active)
    off = inactive_known_agents(active)
    off_note = ""
    if off:
        off_note = f"\n- **Off this session:** {', '.join(_label(a) for a in off)} — MESSAGE 금지."

    def pick(*candidates: str) -> str | None:
        for c in candidates:
            if c in active:
                return c
        return None

    execute = pick("cursor") or (active[0] if len(active) == 1 else None)
    decompose = pick("codex")
    review = pick("claude", "kimi_work")
    delegate_lines: list[str] = []
    if execute:
        delegate_lines.append(f"execute/patch → {_label(execute)}")
    if decompose and decompose != execute:
        delegate_lines.append(f"decompose/verify → {_label(decompose)}")
    elif not decompose:
        alt = next((a for a in active if a not in {execute, review}), None)
        if alt and alt != execute:
            delegate_lines.append(f"decompose/verify → {_label(alt)}")
    if review and review not in {execute, decompose}:
        delegate_lines.append(f"blind-spot review → {_label(review)}")
    delegate = "; ".join(delegate_lines) if delegate_lines else peer_labels

    return (
        "[Delegator · supervisor preset]\n"
        "Harness Supervisor seat: 턴 리드로 phase/GO를 제안하고, "
        "in-room peer에게 scoped review를 위임하세요. "
        f"**Active peers:** {peer_labels}.{off_note}\n"
        f"- 위임 매핑(가능한 seat만): {delegate}.\n"
        "- Human gate·fork·BLOCK은 Human에게만 올리세요.\n"
        '- 동료 위임: envelope `act: MESSAGE`, `to: <agent>` — **active roster에 있는 id만**.'
    )


def peer_coordination_hint(active: list[str], self_agent: str) -> str:
    peers = [a for a in active if a != self_agent.strip().lower()]
    if not peers:
        return "solo agent this turn"
    return ", ".join(_label(a) for a in peers)


# R2+ sequential: review peers → decompose/verify → execute last.
_REVIEW_ROUND2_PRIORITY: tuple[str, ...] = ("claude", "kimi_work", "codex", "cursor")


def review_round2_order(agents: list[str]) -> list[str]:
    """Filter ``agents`` into R2+ sequential speak order (review → verify → execute)."""
    pool = {str(a).strip().lower(): str(a).strip().lower() for a in agents if str(a).strip()}
    ordered = [aid for aid in _REVIEW_ROUND2_PRIORITY if aid in pool]
    for aid in agents:
        key = str(aid).strip().lower()
        if key and key not in ordered:
            ordered.append(key)
    return ordered
