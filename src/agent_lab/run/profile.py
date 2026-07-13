"""Run Profile System (N2) — four named flag presets.

Four profiles cover the main operational modes. Individual AGENT_LAB_* overrides
always take precedence over profile defaults (profiles only fill in unset flags).

Profiles:
  fast        — single agent, auto-approve low-risk, Oracle mock
  balanced    — supervisor preset, human gate, Oracle live (default)
  thorough    — supervisor + adversarial + live judge, human gate, Oracle live
  autonomous  — mission loop + auto-approve medium-risk, Oracle live

F2: every *feature* flag in FLAG_REGISTRY has ≥1 profile owner.
  - ``flags`` — applied defaults (env fill-in)
  - ``owns`` — membership only (no apply); documents which profile owns the flag
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Literal

RunProfile = Literal["fast", "balanced", "thorough", "autonomous"]

# Throughput / lean context (membership; applied defaults stay in flags).
_FAST_OWNS: frozenset[str] = frozenset(
    {
        "AGENT_LAB_EFFICIENCY",
        "AGENT_LAB_EFFICIENCY_RECENT_TURNS",
        "AGENT_LAB_EFFICIENCY_MAX_PIN_MSGS",
        "AGENT_LAB_EFFICIENCY_PIN_BUDGET_PCT",
        "AGENT_LAB_EFFICIENCY_MAX_AGREED",
        "AGENT_LAB_EFFICIENCY_MAX_OPEN",
        "AGENT_LAB_EFFICIENCY_REPLY_HINT",
        "AGENT_LAB_EFFICIENCY_CONSENSUS_ROUNDS",
        "AGENT_LAB_EFFICIENCY_CONSENSUS_CALLS",
        "AGENT_LAB_EFFICIENCY_DEBATE_ROUNDS",
        "AGENT_LAB_COMPACT_TOOL_OUTPUT",
        "AGENT_LAB_COMPACT_TOOL_CHARS",
        "AGENT_LAB_F2_ARTIFACT_ONLY",
        "AGENT_LAB_CHAT_JSONL_TAIL_LINES",
        "AGENT_LAB_CHARS_PER_TOKEN",
        "AGENT_LAB_EPHEMERAL_SYSTEM_MAX_KEEP",
        "AGENT_LAB_R15",
        "AGENT_LAB_QUIET_ACCESS_LOG",
        "AGENT_LAB_KIMI_WORK_WARM_ON_STARTUP",
        "AGENT_LAB_KIMI_WORK_KEEP_DAIMON_ON_SHUTDOWN",
        "AGENT_LAB_KIMI_WORK_PROBE_TTL_S",
        "AGENT_LAB_CLI_RETRY_ROOM_ONLY",
        "AGENT_LAB_ROOM_SERVER_TIMEOUT_SEC",
        "AGENT_LAB_SKIP_AUTH_BOOTSTRAP",
        "AGENT_LAB_CLAUDE_HEADLESS_PROBE",
    }
)

# Max verification / gates.
_THOROUGH_OWNS: frozenset[str] = frozenset(
    {
        "AGENT_LAB_ANTIDRIFT",
        "AGENT_LAB_DEBATE_CONVERGENCE_GATE",
        "AGENT_LAB_DEBATE_CONVERGENCE_THRESHOLD",
        "AGENT_LAB_PLAN_COLD_CRITIC",
        "AGENT_LAB_SYNTAX_GATE",
        "AGENT_LAB_EVAL_HARNESS",
        "AGENT_LAB_WEAKNESS_MINER",
        "AGENT_LAB_PLAYBOOK",
        "AGENT_LAB_PLAYBOOK_PATH",
        "AGENT_LAB_EVENT_VALIDATE",
        "AGENT_LAB_EVENT_MEMORY",
        "AGENT_LAB_FACILITATOR_LIVE",
        "AGENT_LAB_ENVELOPE_STRICT",
        "AGENT_LAB_DIFF_SAFETY",
        "AGENT_LAB_SANDBOX_POLICY",
        "AGENT_LAB_SANDBOX_RUNTIME",
        "AGENT_LAB_REPO_MAP",
        "AGENT_LAB_REPO_MAP_TOKENS",
        "AGENT_LAB_JUDGE_MODEL",
        "AGENT_LAB_ORACLE_MODEL",
        "AGENT_LAB_GOAL_ORACLE_MODEL",
        "AGENT_LAB_MAX_PEER_REVIEW_ROUNDS",
        "AGENT_LAB_KIMI_WORK_ENVELOPE_STRICT",
        "AGENT_LAB_TURN_METRICS",
        "AGENT_LAB_OUTCOME_LEDGER",
        "AGENT_LAB_DOGFOOD_EXECUTE_OUTCOMES",
        "AGENT_LAB_FEEDBACK_ADVISOR",
        "AGENT_LAB_FEEDBACK_MIN_SAMPLE",
        "AGENT_LAB_FEEDBACK_EXPLORE_RATE",
        "AGENT_LAB_TURN_CONTRACT_MODE",
        "AGENT_LAB_OUTCOMES_ROOT",
        "AGENT_LAB_PLAN_FSM_SKILL_FIRST",
        "AGENT_LAB_CORRECTION_HARVESTER",
    }
)

# Mission loop / auto-advance / budgets.
_AUTONOMOUS_OWNS: frozenset[str] = frozenset(
    {
        "AGENT_LAB_HARNESS_PROPOSER",
        "AGENT_LAB_REGRESSION_GATE",
        "AGENT_LAB_HARNESS_INBOX",
        "AGENT_LAB_MISSION_AUTORUN",
        "AGENT_LAB_MISSION_BUDGET_USD",
        "AGENT_LAB_BUDGET_WARN_PCT",
        "AGENT_LAB_DRIFT_AUDIT",
        "AGENT_LAB_DRIFT_AUDIT_INTERVAL",
        "AGENT_LAB_ORCHESTRATION_DRIFT_RECONCILE",
        "AGENT_LAB_ORCHESTRATION_DRIFT_ESCALATE_AFTER",
        "AGENT_LAB_GOAL_LOOP",
        "AGENT_LAB_GOAL_ORACLE_LIVE",
        "AGENT_LAB_GOAL_AUTO_CONTINUE",
        "AGENT_LAB_LOOP_PROBE",
        "AGENT_LAB_LOOP_MAX_COST_TIER",
        "AGENT_LAB_LOOP_MAX_ROUNDS",
        "AGENT_LAB_LOOP_MAX_CALLS",
        "AGENT_LAB_LOOP_MAX_TOKEN_EST",
        "AGENT_LAB_GATE_SCOPE",
        "AGENT_LAB_STAGE_ROUTING",
        "AGENT_LAB_TURN_METRICS",
        "AGENT_LAB_OUTCOME_LEDGER",
        "AGENT_LAB_DOGFOOD_EXECUTE_OUTCOMES",
        "AGENT_LAB_FEEDBACK_ADVISOR",
        "AGENT_LAB_FEEDBACK_MIN_SAMPLE",
        "AGENT_LAB_FEEDBACK_EXPLORE_RATE",
        "AGENT_LAB_TURN_CONTRACT_MODE",
        "AGENT_LAB_OUTCOMES_ROOT",
        "AGENT_LAB_PLAN_FSM_SKILL_FIRST",
        "AGENT_LAB_CORRECTION_HARVESTER",
    }
)
_BALANCED_OWNS: frozenset[str] = frozenset(
    {
        "AGENT_LAB_RUN_PROFILE",
        "AGENT_LAB_CHECKPOINT",
        "AGENT_LAB_TRACE",
        "AGENT_LAB_CRASH_RECOVERY",
        "AGENT_LAB_CLARIFIER",
        "AGENT_LAB_CLARIFIER_INTERVIEW",
        "AGENT_LAB_CLARIFIER_MIN_CHARS",
        "AGENT_LAB_AUTO_PLAN_SCRIBE",
        "AGENT_LAB_TURN_POLICY",
        "AGENT_LAB_TURN_CONTRACT_MODE",
        "AGENT_LAB_ORCHESTRATION_DRIFT_RECONCILE",
        "AGENT_LAB_ORCHESTRATION_DRIFT_ESCALATE_AFTER",
        "AGENT_LAB_SESSION_METRICS_MCP",
        "AGENT_LAB_RECENT_TURNS",
        "AGENT_LAB_MAX_THREAD_CHARS",
        "AGENT_LAB_NUMBERED_CONTEXT",
        "AGENT_LAB_CONTEXT_WARN_PCT",
        "AGENT_LAB_CONTEXT_CRITICAL_PCT",
        "AGENT_LAB_MAX_AGREED_ITEMS",
        "AGENT_LAB_MAX_OPEN_ITEMS",
        "AGENT_LAB_MAX_GATE_LINES",
        "AGENT_LAB_MAX_STATUS_TAGS",
        "AGENT_LAB_MAX_CONSENSUS_ROUNDS",
        "AGENT_LAB_MAX_CONSENSUS_CALLS",
        "AGENT_LAB_DEBATE_ROUNDS",
        "AGENT_LAB_MAX_TASKS_PER_TURN",
        "AGENT_LAB_SCRIBE_RECENT_TURNS",
        "AGENT_LAB_SCRIBE_MAX_CHARS",
        "AGENT_LAB_SCRIBE_FULL",
        "AGENT_LAB_LEGACY_ENDORSE",
        "AGENT_LAB_GUIDANCE_TIER",
        "AGENT_LAB_STRUCTURED_ENVELOPE",
        "AGENT_LAB_TOPIC_ROUTER",
        "AGENT_LAB_PLAN_WORKFLOW",
        "AGENT_LAB_MISSION_DUAL_WRITE",
        "AGENT_LAB_MISSION_DUAL_WRITE_SESSIONS",
        "AGENT_LAB_PLAN_INBOX",
        "AGENT_LAB_PIPELINE",
        "AGENT_LAB_DYNAMIC_ROOM",
        "AGENT_LAB_DISPATCH_MAX_FANOUT",
        "AGENT_LAB_COMMS_COMPACT",
        "AGENT_LAB_CLARITY_THRESHOLD",
        "AGENT_LAB_CLARITY_TOPOLOGY",
        "AGENT_LAB_ROOM_ROLES",
        "AGENT_LAB_ROOM_MODELS",
        "AGENT_LAB_ROOM_SUBSTITUTION",
        "AGENT_LAB_SESSION_TOKEN_BUDGET",
        "AGENT_LAB_SESSION_HARD_CAP",
        "AGENT_LAB_RUN_LOCK_BACKEND",
        "AGENT_LAB_PIPELINE_PYTHON",
        "AGENT_LAB_INBOX_CALLER_AGENT",
        "AGENT_LAB_INBOX_POLICY_LANE",
        "AGENT_LAB_DISCUSS_OBJECTIONS",
        "AGENT_LAB_WISDOM_IN_CONTEXT",
        "AGENT_LAB_AGENT_LEARNINGS",
        "AGENT_LAB_EXECUTE_INBOX",
        "AGENT_LAB_INBOX_MODE",
        "AGENT_LAB_ORCHESTRATOR_INBOX_HARVEST",
        "AGENT_LAB_SKILL_DRAFTS",
        "AGENT_LAB_INBOX_TIMEOUT_SEC",
        "AGENT_LAB_INBOX_POLL_SEC",
        "AGENT_LAB_WISDOM_INDEX",
        "AGENT_LAB_WISDOM_CROSS_SESSION",
        "AGENT_LAB_WISDOM_MCP",
        "AGENT_LAB_WISDOM_PATH",
        "AGENT_LAB_CODEX_PROXY",
        "AGENT_LAB_EXTERNAL_TOOLS",
        "AGENT_LAB_EXTERNAL_TOOL_TIMEOUT",
        "AGENT_LAB_CODE_MEMORY_MCP",
        "AGENT_LAB_CODE_MEMORY_MODE",
        "AGENT_LAB_NATIVE_HOOKS",
        "AGENT_LAB_HOOK_TIMEOUT_S",
        "AGENT_LAB_CLI_RETRY_MAX",
        "AGENT_LAB_CLI_RETRY_BASE_SEC",
        "AGENT_LAB_KIMI_WORK_MODEL",
        "AGENT_LAB_KIMI_WORK_LOOP_PHASE",
        "AGENT_LAB_KIMI_WORK_INBOX_BRIDGE",
        "AGENT_LAB_MODEL_CATALOG_REFRESH",
        "AGENT_LAB_MODEL_CATALOG_REFRESH_CODEX",
        "AGENT_LAB_MODEL_CATALOG_TTL_S",
        "AGENT_LAB_QUARTER_BUDGET_USD",
        "AGENT_LAB_QUARTER_BUDGET_WARN_PCT",
        "AGENT_LAB_QUARTER_BUDGET_DEMOTE",
        "AGENT_LAB_RISK_PIN",
        "AGENT_LAB_RULE_SYNC",
        "AGENT_LAB_MISSION_SCHEDULER",
        "AGENT_LAB_MISSION_SCHEDULER_INTERVAL_S",
        "AGENT_LAB_ACTIVITY_QUEUE_RECOVERY",
        "AGENT_LAB_ACTIVITY_RECOVERY_INTERVAL_S",
        "AGENT_LAB_OFFLINE_ACTIVE_CAP",
        "AGENT_LAB_OFFLINE_WATCH_CAP",
        "AGENT_LAB_RESEARCH_MCP_CRITIC_LIVE",
        "SUPERVISOR_DELEGATOR",
    }
)


@dataclass(frozen=True, slots=True)
class RunProfileConfig:
    profile: RunProfile
    description: str
    flags: dict[str, str] = field(default_factory=dict)
    owns: frozenset[str] = field(default_factory=frozenset)

    def owned_flags(self) -> frozenset[str]:
        return frozenset(self.flags) | self.owns


_PROFILE_CONFIGS: dict[str, RunProfileConfig] = {
    "fast": RunProfileConfig(
        profile="fast",
        description="Single-agent, auto-approve low-risk changes, Oracle mock — fastest throughput",
        flags={
            "AGENT_LAB_ROOM_PRESET": "fast",
            "AGENT_LAB_AUTO_APPROVE_THRESHOLD": "low",
            "AGENT_LAB_AUTO_APPROVE_TIMEOUT_SEC": "0",
            "AGENT_LAB_ORACLE_LIVE": "",
            "AGENT_LAB_ADVERSARIAL_LIVE": "",
            "AGENT_LAB_JUDGE_LIVE": "",
        },
        owns=_FAST_OWNS,
    ),
    "balanced": RunProfileConfig(
        profile="balanced",
        description="Supervisor preset, human gate on every change, Oracle live — safe default",
        flags={
            "AGENT_LAB_ROOM_PRESET": "supervisor",
            "AGENT_LAB_ORACLE_LIVE": "1",
            "AGENT_LAB_ADVERSARIAL_LIVE": "",
            "AGENT_LAB_JUDGE_LIVE": "",
            "AGENT_LAB_TURN_METRICS": "1",
            "AGENT_LAB_OUTCOME_LEDGER": "1",
            "AGENT_LAB_FEEDBACK_ADVISOR": "1",
            "AGENT_LAB_PLAN_FSM_SKILL_FIRST": "1",
            "AGENT_LAB_CORRECTION_HARVESTER": "1",
        },
        owns=_BALANCED_OWNS,
    ),
    "thorough": RunProfileConfig(
        profile="thorough",
        description="Supervisor + adversarial gate + live judge — maximum verification",
        flags={
            "AGENT_LAB_ROOM_PRESET": "supervisor",
            "AGENT_LAB_ORACLE_LIVE": "1",
            "AGENT_LAB_ADVERSARIAL_LIVE": "1",
            "AGENT_LAB_JUDGE_LIVE": "1",
            "AGENT_LAB_PLAN_FSM_SKILL_FIRST": "1",
        },
        owns=_THOROUGH_OWNS,
    ),
    "autonomous": RunProfileConfig(
        profile="autonomous",
        description="Mission loop + auto-approve medium-risk, Oracle live — trusted autonomous mode",
        flags={
            "AGENT_LAB_ROOM_PRESET": "supervisor",
            "AGENT_LAB_AUTO_APPROVE_THRESHOLD": "medium",
            "AGENT_LAB_AUTO_APPROVE_TIMEOUT_SEC": "30",
            "AGENT_LAB_MISSION_LOOP": "1",
            "AGENT_LAB_ORACLE_LIVE": "1",
            "AGENT_LAB_ADVERSARIAL_LIVE": "",
            "AGENT_LAB_JUDGE_LIVE": "",
            "AGENT_LAB_PLAN_FSM_SKILL_FIRST": "1",
        },
        owns=_AUTONOMOUS_OWNS,
    ),
}


def resolve_profile(profile: str | None) -> RunProfileConfig | None:
    """Return the config for a profile name, or None if unknown/unset."""
    if not profile:
        return None
    return _PROFILE_CONFIGS.get(profile.strip().lower())


def default_run_profile() -> str | None:
    """Return the profile name from AGENT_LAB_RUN_PROFILE env var, or ``balanced``."""
    raw = (os.getenv("AGENT_LAB_RUN_PROFILE") or "").strip().lower()
    if resolve_profile(raw) is not None:
        return raw
    if not raw:
        return "balanced"
    return None


def apply_run_profile(profile: str | None, *, overwrite: bool = False) -> dict[str, str]:
    """Apply profile flag defaults to os.environ.

    Only sets flags that are not already set in the environment unless
    *overwrite=True* is passed. Returns the dict of flags that were applied.
    Membership-only ``owns`` entries are not applied.
    """
    cfg = resolve_profile(profile)
    if cfg is None:
        return {}
    applied: dict[str, str] = {}
    for name, value in cfg.flags.items():
        if overwrite or os.getenv(name) is None:
            if value:
                os.environ[name] = value
            elif name in os.environ:
                del os.environ[name]
            applied[name] = value
    return applied


def list_profiles() -> list[RunProfileConfig]:
    """Return all available run profiles in display order."""
    return list(_PROFILE_CONFIGS.values())


def profile_ids() -> tuple[str, ...]:
    return tuple(cfg.profile for cfg in list_profiles())


def flag_profile_membership() -> dict[str, list[str]]:
    """Map flag name → profile ids that own the flag (F2 / N2).

    Ownership = applied ``flags`` keys ∪ membership-only ``owns``.
    Any feature flag still missing an owner is assigned to ``balanced``.
    """
    membership: dict[str, list[str]] = {}
    for cfg in list_profiles():
        for name in cfg.owned_flags():
            membership.setdefault(name, []).append(cfg.profile)

    from agent_lab.runtime_flags import FLAG_REGISTRY

    for row in FLAG_REGISTRY:
        if row.category != "feature":
            continue
        if row.name not in membership:
            membership[row.name] = ["balanced"]
    return membership


def feature_flags_without_owner() -> list[str]:
    """Feature flags that rely on balanced fallback (should be empty after F2)."""
    from agent_lab.runtime_flags import FLAG_REGISTRY

    explicit: set[str] = set()
    for cfg in list_profiles():
        explicit |= set(cfg.owned_flags())
    return sorted(row.name for row in FLAG_REGISTRY if row.category == "feature" and row.name not in explicit)


def profile_catalog() -> dict[str, Any]:
    """Return profile info for /api/profiles."""
    active = default_run_profile()
    membership = flag_profile_membership()
    fallback = feature_flags_without_owner()
    return {
        "profiles": [
            {
                "id": cfg.profile,
                "description": cfg.description,
                "flags": cfg.flags,
                "owns": sorted(cfg.owns),
                "owned_count": len(cfg.owned_flags()),
            }
            for cfg in list_profiles()
        ],
        "default": active,
        "active": active,
        "flag_membership": membership,
        "profile_count": len(_PROFILE_CONFIGS),
        "feature_flags_owned": sum(1 for owners in membership.values() if owners),
        "feature_flags_fallback_balanced": fallback,
    }
