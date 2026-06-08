"""Session context layer toggles (Track C — Overview / bundle policy)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_lab.run_meta import patch_run_meta, read_run_meta

CONTEXT_LAYER_KEYS = frozenset({"mission_wisdom", "repo_tree"})

DEFAULT_CONTEXT_LAYERS: dict[str, bool] = {
    "mission_wisdom": True,
    "repo_tree": True,
}


def get_context_layers(run: dict[str, Any] | None) -> dict[str, bool]:
    base = dict(DEFAULT_CONTEXT_LAYERS)
    raw = (run or {}).get("context_layers")
    if isinstance(raw, dict):
        for key in CONTEXT_LAYER_KEYS:
            if key in raw:
                base[key] = bool(raw[key])
    return base


def mission_wisdom_layer_enabled(run: dict[str, Any] | None) -> bool:
    return get_context_layers(run).get("mission_wisdom", True)


def repo_tree_layer_enabled(run: dict[str, Any] | None) -> bool:
    return get_context_layers(run).get("repo_tree", True)


def should_use_mission_slim_bundle(run_meta: dict[str, Any] | None) -> bool:
    """DISCUSS / PLAN_GATE phases use slimmer context when mission loop is on."""
    from agent_lab.mission_loop import get_mission_loop

    ml = get_mission_loop(run_meta)
    if not ml.get("enabled"):
        return False
    phase = str(ml.get("phase") or "")
    return phase in {"DISCUSS", "PLAN_GATE", "PLAN_REJECT"}


def plan_gate_mcp_warnings(
    run: dict[str, Any] | None,
    actions: list[Any],
) -> list[str]:
    """Soft warnings when verify mentions MCP but session allowlist has none."""
    from agent_lab.command_registry import mcp_allowed_for_agent

    if not actions:
        return []
    mentions_mcp = any(
        "mcp" in str(getattr(a, "verify", "") or "").lower()
        for a in actions
    )
    if not mentions_mcp:
        return []
    if mcp_allowed_for_agent("claude", run) or mcp_allowed_for_agent("codex", run):
        return []
    return [
        "plan verify mentions MCP but session plugin allowlist has no MCP enabled "
        "(enable in Work → Plugins or Settings)"
    ]


def patch_context_layers(folder: Path, updates: dict[str, Any]) -> dict[str, bool]:
    allowed = {k: bool(v) for k, v in updates.items() if k in CONTEXT_LAYER_KEYS}
    if not allowed:
        return get_context_layers(read_run_meta(folder))

    def _patch(run: dict[str, Any]) -> dict[str, Any]:
        layers = get_context_layers(run)
        layers.update(allowed)
        run["context_layers"] = layers
        return run

    patch_run_meta(folder, _patch)
    return get_context_layers(read_run_meta(folder))


def public_context_layers_payload(folder: Path) -> dict[str, Any]:
    run = read_run_meta(folder)
    layers = get_context_layers(run)
    return {"ok": True, "context_layers": layers}
