"""Dynamic agent roster for the resilient room (AGENT_LAB_DYNAMIC_ROOM).

OFF-parity: when the flag is unset, resolve_active_agents returns
``[a for a in (agents or available_agents())]`` byte-stable with the
pre-dynamic room. When ON, it picks the default composition
(cursor+codex+claude), fills unavailable seats from the substitution
priority (KIMI->local), and honors /model env overrides.

The live path only ever yields registry-invokable AgentIds; the
kimi/local substitution is exercised by unit tests with injected
availability and goes live once their adapters land (G006).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Callable, cast

from agent_lab import provider_registry

if TYPE_CHECKING:
    from agent_lab.agents.registry import AgentId

DEFAULT_ROSTER = provider_registry.DEFAULT_ROSTER
DEFAULT_SUBSTITUTION_PRIORITY = provider_registry.DEFAULT_SUBSTITUTION_PRIORITY


def dynamic_room_enabled() -> bool:
    """AGENT_LAB_DYNAMIC_ROOM: gate the dynamic resilient room (additive).

    Default ON (production dogfood): dynamic roster, /login etc. slash commands,
    and credential management via slash. Set AGENT_LAB_DYNAMIC_ROOM=0 to fall
    back to the static cursor/codex/claude room (OFF-parity escape hatch).
    """
    return os.getenv("AGENT_LAB_DYNAMIC_ROOM", "1").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


def dynamic_room_explicitly_disabled() -> bool:
    """True only when the user explicitly opted out of the dynamic room."""
    return os.getenv("AGENT_LAB_DYNAMIC_ROOM", "1").strip().lower() in {
        "0",
        "false",
        "no",
        "off",
    }


def _parse_csv_env(name: str) -> list[str] | None:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return None
    ids = [tok.strip() for tok in raw.split(",") if tok.strip()]
    return ids or None


def normalize_composition_order(composition: list[str]) -> list[str]:
    """Sort agent ids for stable UI and room roster (cursor → codex → claude → spares)."""
    from agent_lab.provider_registry import provider_picker_order

    rank = {pid: index for index, pid in enumerate(provider_picker_order())}
    seen: set[str] = set()
    out: list[str] = []
    for pid in composition:
        key = str(pid).strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(key)
    out.sort(key=lambda pid: rank.get(pid, len(rank)))
    return out


def session_composition_override(*, session_folder: Path | None = None) -> list[str] | None:
    """Composition pinned to THIS session (run.json room_models) — excludes global default.

    This is the only override that should outrank an explicit per-call agent selection:
    the user fixed the roster for this session on purpose. The global default file is a
    fallback for when nothing was selected, not a veto over the current pick.
    """
    if session_folder is None:
        return None
    from agent_lab.run.meta import read_run_meta

    meta = read_run_meta(session_folder)
    raw = meta.get("room_models")
    if isinstance(raw, list):
        ids = normalize_composition_order([str(tok) for tok in raw if str(tok).strip()])
        if ids:
            return ids
    return None


def global_composition_default() -> list[str] | None:
    """Global default composition: ~/.agent-lab/room_models → AGENT_LAB_ROOM_MODELS env."""
    from agent_lab.room.models_config import load_default_room_models

    default = load_default_room_models()
    if default:
        return normalize_composition_order(default)
    env = _parse_csv_env("AGENT_LAB_ROOM_MODELS")
    if env:
        return normalize_composition_order(env)
    return None


def override_composition(*, session_folder: Path | None = None) -> list[str] | None:
    """Explicit composition override: session run.json → default file → process env.

    Kept for requested-less callers (health UI, slash status) that just want the
    resolved "forced" composition. Roster selection uses select_roster(), which
    applies the correct precedence: session override > requested > global default.
    """
    return session_composition_override(session_folder=session_folder) or global_composition_default()


def effective_room_composition(*, session_folder: Path | None = None) -> list[str]:
    """Resolved Room model composition for health UI (includes DEFAULT_ROSTER fallback)."""
    override = override_composition(session_folder=session_folder)
    if override:
        return list(override)
    return list(DEFAULT_ROSTER)


def override_substitution() -> list[str] | None:
    """/model substitution-priority override via AGENT_LAB_ROOM_SUBSTITUTION=kimi,local."""
    return _parse_csv_env("AGENT_LAB_ROOM_SUBSTITUTION")


def select_roster(
    *,
    requested: list[str] | None = None,
    available_ids: list[str],
    size: int | None = None,
    session_folder: Path | None = None,
) -> list[str]:
    """Choose up to ``size`` providers: composition filtered by availability,
    then empty seats filled from the substitution priority.
    """
    # Precedence: session-pinned roster > this call's explicit request > global default.
    # The global default is a fallback for an empty request, never a veto over it —
    # otherwise a saved default (e.g. kimi_work) silently overrides what the user just picked.
    session_override = session_composition_override(session_folder=session_folder)
    if session_override:
        composition = list(session_override)
    elif requested:
        composition = list(requested)
    else:
        composition = global_composition_default() or list(DEFAULT_ROSTER)
    target = size if size is not None else len(composition)
    avail = set(available_ids)

    roster: list[str] = [pid for pid in composition if pid in avail]
    if len(roster) < target:
        for sub in override_substitution() or list(DEFAULT_SUBSTITUTION_PRIORITY):
            if len(roster) >= target:
                break
            if sub not in roster and sub in avail:
                roster.append(sub)
    return roster


def dynamic_available_ids(
    available_fn: Callable[[], list[AgentId]],
    *,
    now: float | None = None,
) -> list[str]:
    """Runtime availability for the dynamic roster: cloud agents + the local floor.

    local is always available (the >=1-agent guarantee). kimi participates in
    selection tests but is excluded from the live invokable set until its adapter
    lands; including only invokable providers keeps the live room safe.
    """
    ids = [str(a) for a in available_fn()]
    # KIMI is a live api substitute when it has a usable account chain.
    from agent_lab.credential_store import get_account_chain

    if "kimi" not in ids and get_account_chain("kimi", now=now):
        ids.append("kimi")
    from agent_lab.kimi import work_provider as kimi_work_provider

    if "kimi_work" not in ids and kimi_work_provider.is_available():
        ids.append("kimi_work")
    if "local" not in ids:
        ids.append("local")
    return ids


def resolve_active_agents(
    agents: list[AgentId] | None,
    available_fn: Callable[[], list[AgentId]],
    *,
    enabled: bool | None = None,
    session_folder: Path | None = None,
) -> list[AgentId]:
    """Flag-gated active-agent resolution used by the room.

    OFF (flag unset): byte-stable with the pre-dynamic ``agents or available_agents()``.
    ON: dynamic roster, restricted to registry-invokable AgentIds at runtime.
    """
    is_on = dynamic_room_enabled() if enabled is None else enabled
    if not is_on:
        return [a for a in (agents or available_fn())]

    from agent_lab.agents.registry import AGENT_IDS

    available = dynamic_available_ids(available_fn)
    # Only a session-pinned roster suppresses the explicit request; the global default
    # must not (select_roster applies it as a fallback when requested is empty).
    session_override = session_composition_override(session_folder=session_folder)
    requested = None if session_override else ([str(a) for a in agents] if agents else None)
    roster = select_roster(
        requested=requested,
        available_ids=available,
        session_folder=session_folder,
    )
    # Live invokable set: default cloud agents + KIMI (api substitute) + the local floor.
    invokable = set(AGENT_IDS) | {"kimi", "kimi_work", "local"}
    return [cast("AgentId", pid) for pid in roster if pid in invokable]
