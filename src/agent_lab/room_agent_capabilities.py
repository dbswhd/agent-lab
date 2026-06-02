"""Per-agent capability profiles (Phase F — asymmetric room agents)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

RUN_AGENT_CAPABILITIES_KEY = "agent_capabilities"
RUN_AGENT_CAPABILITIES_CUSTOM_KEY = "agent_capabilities_custom"

DEFAULT_CAPABILITIES: dict[str, dict[str, Any]] = {
    "cursor": {
        "tools": ["sdk_edit"],
        "cwd_role": "primary",
        "label": "execute · SDK patch",
    },
    "codex": {
        "tools": ["codex_cli"],
        "cwd_role": "repo",
        "label": "decompose · verify · sandbox",
    },
    "claude": {
        "tools": ["read_only"],
        "cwd_role": "review",
        "label": "risk · read-only review",
    },
}

SPECIALIST_CAPABILITIES: dict[str, dict[str, Any]] = {
    "cursor": {
        "tools": ["sdk_edit"],
        "cwd_role": "execute",
        "label": "R2 patch · SDK",
        "restrictions": ["R2 only — apply Codex/Claude R1 findings"],
    },
    "codex": {
        "tools": ["codex_cli", "sandbox"],
        "cwd_role": "repo",
        "label": "R1 decompose · verify",
        "restrictions": ["no unilateral execute without plan"],
    },
    "claude": {
        "tools": ["read_only"],
        "cwd_role": "review",
        "label": "R1 risk · counter-evidence",
        "restrictions": ["no file writes"],
    },
}


def normalize_capability(raw: dict[str, Any] | None) -> dict[str, Any]:
    raw = raw or {}
    tools = raw.get("tools") or []
    if not isinstance(tools, list):
        tools = []
    out: dict[str, Any] = {
        "tools": [str(t).strip() for t in tools if str(t).strip()],
        "cwd_role": str(raw.get("cwd_role") or "primary").strip().lower(),
        "label": str(raw.get("label") or "").strip()[:120],
    }
    restrictions = raw.get("restrictions") or []
    if isinstance(restrictions, list) and restrictions:
        out["restrictions"] = [
            str(r).strip() for r in restrictions if str(r).strip()
        ][:6]
    cwd_path = str(raw.get("cwd_path") or "").strip()
    if cwd_path:
        out["cwd_path"] = cwd_path[:500]
    return out


def get_agent_capabilities(run_meta: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not run_meta:
        return {k: normalize_capability(v) for k, v in DEFAULT_CAPABILITIES.items()}
    raw = run_meta.get(RUN_AGENT_CAPABILITIES_KEY)
    if not isinstance(raw, dict):
        return {k: normalize_capability(v) for k, v in DEFAULT_CAPABILITIES.items()}
    out: dict[str, dict[str, Any]] = {}
    for agent in ("cursor", "codex", "claude"):
        block = raw.get(agent)
        if isinstance(block, dict):
            out[agent] = normalize_capability(block)
        else:
            out[agent] = normalize_capability(DEFAULT_CAPABILITIES.get(agent))
    return out


def write_agent_capabilities(
    run_meta: dict[str, Any],
    caps: dict[str, dict[str, Any]],
    *,
    mark_custom: bool = True,
) -> None:
    run_meta[RUN_AGENT_CAPABILITIES_KEY] = {
        agent: normalize_capability(caps.get(agent) or DEFAULT_CAPABILITIES.get(agent))
        for agent in ("cursor", "codex", "claude")
    }
    if mark_custom:
        run_meta[RUN_AGENT_CAPABILITIES_CUSTOM_KEY] = True


def capabilities_public_payload(
    run_meta: dict[str, Any] | None,
    permissions: dict[str, Any] | None = None,
) -> dict[str, Any]:
    caps = get_agent_capabilities(run_meta)
    resolved = {
        agent: agent_capability_cwd(agent, permissions, run_meta)
        for agent in ("cursor", "codex", "claude")
    }
    return {
        "agent_capabilities": caps,
        "agent_capabilities_custom": bool(
            (run_meta or {}).get(RUN_AGENT_CAPABILITIES_CUSTOM_KEY)
        ),
        "resolved_cwd": resolved,
    }


def ensure_specialist_capabilities(run_meta: dict[str, Any]) -> None:
    write_agent_capabilities(run_meta, SPECIALIST_CAPABILITIES)


def _binding_path(run_meta: dict[str, Any] | None) -> Path | None:
    if not run_meta:
        return None
    binding = run_meta.get("workspace_binding")
    if isinstance(binding, dict) and binding.get("path"):
        try:
            p = Path(str(binding["path"])).resolve()
            if p.is_dir():
                return p
        except OSError:
            return None
    return None


def _resolve_role_root(
    agent: str,
    cwd_role: str,
    permissions: dict[str, Any] | None,
    run_meta: dict[str, Any] | None,
) -> Path:
    from agent_lab.workspace_roots import (
        discuss_primary_workspace,
        pipeline_root,
        primary_workspace,
        project_root,
    )

    caps = get_agent_capabilities(run_meta)
    cap = caps.get(str(agent).strip().lower()) or {}
    custom = str(cap.get("cwd_path") or "").strip()
    if custom:
        try:
            p = Path(custom).expanduser().resolve()
            if p.is_dir():
                return p
        except OSError:
            pass

    binding = _binding_path(run_meta)
    role = (cwd_role or "primary").strip().lower()
    if role == "execute" and binding:
        return binding
    if role == "repo":
        pipe = pipeline_root()
        if pipe is not None:
            return pipe.resolve()
        if binding:
            return binding
    if role == "review":
        root = project_root()
        if root is not None:
            return root.resolve()
    return discuss_primary_workspace(permissions)


def agent_capability_cwd(
    agent: str,
    permissions: dict[str, Any] | None,
    run_meta: dict[str, Any] | None,
) -> str:
    caps = get_agent_capabilities(run_meta)
    cap = caps.get(str(agent).strip().lower()) or normalize_capability({})
    root = _resolve_role_root(
        agent, str(cap.get("cwd_role") or "primary"), permissions, run_meta
    )
    return str(root.resolve())


def agent_workspace_lines(
    agent: str,
    permissions: dict[str, Any] | None,
    run_meta: dict[str, Any] | None,
) -> str:
    """Asymmetric workspace block for one agent (F1)."""
    caps = get_agent_capabilities(run_meta)
    cap = caps.get(str(agent).strip().lower()) or normalize_capability({})
    cwd = agent_capability_cwd(agent, permissions, run_meta)
    tools = ", ".join(cap.get("tools") or []) or "text"
    label = cap.get("label") or cap.get("cwd_role") or agent
    lines = [
        f"Agent workspace ({agent} · {label}):",
        f"  - cwd: {cwd}",
        f"  - tools: {tools}",
    ]
    for r in cap.get("restrictions") or []:
        lines.append(f"  - restriction: {r}")
    return "\n".join(lines)


def capability_preamble_block(
    agent: str,
    run_meta: dict[str, Any] | None,
    *,
    parallel_round: int = 1,
) -> str:
    caps = get_agent_capabilities(run_meta)
    cap = caps.get(str(agent).strip().lower())
    if not cap:
        return ""
    profile = str((run_meta or {}).get("turn_profile") or "").strip().lower()
    parts = [f"[Capability · {agent}]", cap.get("label") or ""]
    if profile == "specialist":
        if parallel_round == 1 and agent in ("cursor",):
            parts.append("이번 라운드(R1)에는 Codex·Claude만 발화 — 대기.")
        elif parallel_round == 2 and agent in ("codex", "claude"):
            parts.append("R1 완료 — R2는 Cursor 패치 검토만.")
        elif parallel_round == 2 and agent == "cursor":
            parts.append(
                "R2: Codex/Claude R1 발화와 CHALLENGE를 반영해 패치·실행 제안."
            )
    restrictions = cap.get("restrictions") or []
    if restrictions:
        parts.append("제한: " + "; ".join(restrictions))
    text = "\n".join(p for p in parts if p and str(p).strip())
    return text.strip()


def merge_agent_permissions(
    agent: str,
    permissions: dict[str, Any] | None,
    run_meta: dict[str, Any] | None,
) -> dict[str, Any]:
    """Overlay capability tool flags onto session permissions (F1)."""
    out: dict[str, Any] = dict(permissions or {})
    caps = get_agent_capabilities(run_meta)
    cap = caps.get(str(agent).strip().lower()) or {}
    tools = {str(t).strip().lower() for t in (cap.get("tools") or [])}
    block = dict(out.get(agent) or {})
    if "sdk_edit" in tools:
        block["cursor_sdk"] = True
    if "codex_cli" in tools or "sandbox" in tools:
        block["codex_cli"] = True
    if "read_only" in tools:
        block["read_only"] = True
    out[agent] = block
    return out


def specialist_round_agents(
    agents: list[str],
    parallel_round: int,
) -> list[str]:
    """F3: R1 codex+claude parallel; R2 cursor sequential."""
    pool = {str(a).strip().lower() for a in agents if str(a).strip()}
    if parallel_round == 1:
        ordered = [a for a in ("codex", "claude") if a in pool]
        return ordered or [a for a in agents if str(a).strip()][:2]
    if parallel_round == 2:
        ordered = [a for a in ("cursor",) if a in pool]
        return ordered or [str(agents[-1]).strip().lower()] if agents else []
    return [str(a).strip().lower() for a in agents if str(a).strip()]
