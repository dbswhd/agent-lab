"""Staged Loop readiness for Kimi Work (B-track).

Phase 1: tools + structured envelope; Human inbox MCP waived in loop_blockers.
Phase 2 (default): inbox bridge wired — loop_blockers also require supports_inbox_mcp.

Set ``AGENT_LAB_KIMI_WORK_LOOP_PHASE=1`` to waive inbox in Loop gate during rollout.
"""

from __future__ import annotations

import os

# Daimon features advertised for Loop phase 1 (discuss/consensus lane).
# ``capabilities.get`` is the RPC used to fetch this list — not a feature name daimon lists.
KIMI_WORK_LOOP_PHASE1_FEATURES: frozenset[str] = frozenset(
    {
        "conversations.create",
        "conversations.send",
        "workspace.openProject",
    }
)

# Reserved for phase 2 inbox bridge (not probed until phase >= 2).
KIMI_WORK_LOOP_PHASE2_FEATURES: frozenset[str] = frozenset(
    {
        "inbox.askHuman",
        "inbox.proposeBuild",
    }
)


def kimi_work_loop_phase() -> int:
    raw = (os.getenv("AGENT_LAB_KIMI_WORK_LOOP_PHASE") or "2").strip()
    try:
        return max(1, min(int(raw), 2))
    except ValueError:
        return 1


def kimi_work_loop_waives_inbox_mcp() -> bool:
    """True when Loop may proceed without supports_inbox_mcp on kimi_work."""
    return kimi_work_loop_phase() < 2


def kimi_work_loop_tool_features_ok(features: object) -> bool:
    if not isinstance(features, list):
        return False
    normalized = {str(item).strip() for item in features if str(item).strip()}
    return KIMI_WORK_LOOP_PHASE1_FEATURES <= normalized


def kimi_work_loop_inbox_features_ok(features: object) -> bool:
    if not isinstance(features, list):
        return False
    normalized = {str(item).strip() for item in features if str(item).strip()}
    return KIMI_WORK_LOOP_PHASE2_FEATURES <= normalized


def kimi_work_envelope_strict() -> bool:
    """When true, live envelope probe failure sets supports_json_envelope=False (fail-closed)."""
    raw = (os.getenv("AGENT_LAB_KIMI_WORK_ENVELOPE_STRICT") or "0").strip().lower()
    return raw in ("1", "true", "yes", "on")
