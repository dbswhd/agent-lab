"""Curated AGENT_LAB_* env flag registry for API/CLI discoverability."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Literal

from agent_lab.api_diagnostics import mask_tool_path
from agent_lab.env_flags import is_truthy

FlagCategory = Literal["feature", "infra", "test", "internal"]


@dataclass(frozen=True)
class FlagDef:
    name: str
    category: FlagCategory
    description: str
    default: str = ""
    mask_value: bool = False


# Keep in sync with .env.example and docs/USER-GUIDE.md § Feature flags.
FLAG_REGISTRY: tuple[FlagDef, ...] = (
    # --- infra ---
    FlagDef("AGENT_LAB_ROOT", "infra", "Project root path", mask_value=True),
    FlagDef("AGENT_LAB_DEV_ROOT", "infra", "Dev override when bundled .app runtime", mask_value=True),
    FlagDef("AGENT_LAB_SESSIONS_DIR", "infra", "Sessions directory", mask_value=True),
    FlagDef("AGENT_LAB_CONFIG_DIR", "infra", "Override ~/.agent-lab config dir", mask_value=True),
    FlagDef("AGENT_LAB_CONFIG_PATH", "infra", "Override config.toml path", mask_value=True),
    FlagDef("AGENT_LAB_LOG_DIR", "infra", "API/boot log directory", mask_value=True),
    FlagDef("AGENT_LAB_API_PORT", "infra", "FastAPI listen port", default="8765"),
    FlagDef("AGENT_LAB_WEB_URL", "infra", "Web UI base URL for deep links"),
    FlagDef("AGENT_LAB_UI_ARTIFACT_DIR", "infra", "UI smoke artifact output dir", mask_value=True),
    FlagDef("AGENT_LAB_HOOKS_PATH", "infra", "Room hooks.toml path", mask_value=True),
    FlagDef("AGENT_LAB_PROVIDER", "infra", "Classic graph backend: codex | openai | anthropic"),
    FlagDef("AGENT_LAB_CODEX_PROXY_URL", "infra", "Codex openai-oauth proxy base URL"),
    FlagDef("AGENT_LAB_BUNDLE_PYTHON", "infra", "Bundled .app Python path hint", mask_value=True),
    # --- feature: mission / execute ---
    FlagDef("AGENT_LAB_MISSION_LOOP", "feature", "Verified mission loop FSM"),
    FlagDef(
        "AGENT_LAB_MISSION_DUAL_WRITE",
        "feature",
        "Opt-in legacy route to Mission journal migration bridge (default off)",
    ),
    FlagDef(
        "AGENT_LAB_MISSION_DUAL_WRITE_SESSIONS",
        "feature",
        "Comma-separated session IDs allowed to use the dual-write bridge when enabled (empty disables the bridge)",
    ),
    FlagDef(
        "AGENT_LAB_MISSION_AUTHORITY",
        "feature",
        "Journal-owned Mission Inbox authority for the selected bounded cohort (default off)",
    ),
    FlagDef(
        "AGENT_LAB_MISSION_AUTHORITY_SESSIONS",
        "feature",
        "Comma-separated session IDs allowed to use journal-owned Mission Inbox authority (empty disables it)",
    ),
    FlagDef(
        "AGENT_LAB_MISSION_UI_READ_MODEL",
        "feature",
        "Journal-first read-model for migrated sessions; legacy sessions remain server-side fallback",
        default="1",
    ),
    FlagDef(
        "AGENT_LAB_CONTEXT_RECIPE",
        "feature",
        "CX8 select_context()-based bundle_recipe.py shadow computation (default off; not yet wired "
        "into build_context_bundle's live per-turn path -- gates only whether a dogfood/eval harness "
        "is allowed to opt into calling build_manifest_via_recipe() at all)",
        default="0",
    ),
    FlagDef(
        "AGENT_LAB_STAGE_ROUTING", "feature", "Phase-aware single-vs-panel routing (stage-aware selective; default off)"
    ),
    FlagDef(
        "AGENT_LAB_ANTIDRIFT",
        "feature",
        "Structural anti-drift defenses for panel turns (state re-injection, unanimity red-team, fresh-eyes critic seat; default off)",
    ),
    FlagDef(
        "AGENT_LAB_DEBATE_CONVERGENCE_GATE",
        "feature",
        "Interview-style debate convergence scoring — early-exit debate/endorse when convergence ≥ threshold (default off)",
    ),
    FlagDef(
        "AGENT_LAB_DEBATE_CONVERGENCE_THRESHOLD",
        "feature",
        "Debate convergence advance threshold 0..1 (default 0.75)",
        default="0.75",
    ),
    FlagDef(
        "AGENT_LAB_CHECKPOINT",
        "feature",
        "Snapshot run.json FSM state at each phase transition to a per-session checkpoints.jsonl for manual resume (default ON; opt-out via =0)",
        default="1",
    ),
    FlagDef(
        "AGENT_LAB_REPO_MAP",
        "feature",
        "Symbol-graph repo-map (ast def/ref ranking) replacing the plain repo tree in agent context (default off)",
    ),
    FlagDef(
        "AGENT_LAB_REPO_MAP_TOKENS",
        "feature",
        "Token budget for the symbol-graph repo-map output (default 1024)",
        default="1024",
    ),
    FlagDef(
        "AGENT_LAB_COMPACT_TOOL_OUTPUT",
        "feature",
        "Deterministically truncate over-length code-fence tool/shell output in pre-current-turn agent messages before char-trim (default off)",
    ),
    FlagDef(
        "AGENT_LAB_COMPACT_TOOL_CHARS",
        "feature",
        "Per-code-fence-block char cap for tool-output compaction (default 2000)",
        default="2000",
    ),
    FlagDef(
        "AGENT_LAB_CHAT_JSONL_TAIL_LINES",
        "feature",
        "When set, load_session_messages parses only the last N chat.jsonl lines (perf; may break old L refs)",
    ),
    FlagDef(
        "AGENT_LAB_CHARS_PER_TOKEN",
        "feature",
        "Heuristic chars-per-token for estimated usage when provider usage is absent (default 2.0)",
        default="2.0",
    ),
    FlagDef(
        "AGENT_LAB_EPHEMERAL_SYSTEM_MAX_KEEP",
        "feature",
        "Max peer-digest + synthesis system messages kept in prepare_recent_messages (default 3)",
        default="3",
    ),
    FlagDef(
        "AGENT_LAB_SYNTAX_GATE",
        "feature",
        "Hard-block a pending execution's merge when changed *.py fails ast/py_compile (Python-only; lint non-blocking; default ON; opt-out via =0)",
        default="1",
    ),
    FlagDef(
        "AGENT_LAB_SANDBOX_POLICY",
        "feature",
        "Resolve a typed sandbox policy at the worktree verify subprocess seam (default ON; worktree runtime => output identical; opt-out via =0)",
        default="1",
    ),
    FlagDef(
        "AGENT_LAB_SANDBOX_RUNTIME",
        "feature",
        "Sandbox runtime when AGENT_LAB_SANDBOX_POLICY is on: worktree|docker (docker falls back to worktree + records intent; default worktree)",
        default="worktree",
    ),
    FlagDef(
        "AGENT_LAB_EVAL_HARNESS",
        "feature",
        "SWE-bench-style FAIL_TO_PASS/PASS_TO_PASS scorer route POST /api/eval/score (default ON; pure stateless compute; opt-out via =0)",
        default="1",
    ),
    FlagDef(
        "AGENT_LAB_EVENT_MEMORY",
        "feature",
        "Namespace KV memory store route POST /api/memory/eval (default ON; pure stateless compute; opt-out via =0)",
        default="1",
    ),
    FlagDef(
        "AGENT_LAB_EVENT_VALIDATE",
        "feature",
        "Validate + drop invalid live-log events in Room turns via event_schema (default OFF; behavior change)",
    ),
    FlagDef("AGENT_LAB_LOOP_PROBE", "feature", "Runtime static loop capability probe", default="1"),
    FlagDef(
        "AGENT_LAB_LOOP_PROBE_CACHE",
        "infra",
        "Override loop probe cache path",
        mask_value=True,
    ),
    FlagDef(
        "AGENT_LAB_LOOP_EVAL_REGISTRY",
        "infra",
        "Override loop_model_eval.json path",
        mask_value=True,
    ),
    FlagDef(
        "AGENT_LAB_LOOP_MAX_COST_TIER",
        "feature",
        "Loop max model cost tier (low|medium|high)",
        default="high",
    ),
    FlagDef("AGENT_LAB_LOOP_MAX_ROUNDS", "feature", "Loop mode max consensus rounds", default="4"),
    FlagDef("AGENT_LAB_LOOP_MAX_CALLS", "feature", "Loop mode max agent calls", default="12"),
    FlagDef(
        "AGENT_LAB_LOOP_MAX_TOKEN_EST",
        "feature",
        "Loop mode max token estimate budget",
        default="500000",
    ),
    FlagDef("AGENT_LAB_MISSION_AUTORUN", "feature", "Auto-advance mission loop after approve"),
    FlagDef(
        "AGENT_LAB_MISSION_TOPOLOGY",
        "feature",
        "Arm-time deterministic topology decision (choose_topology) recorded to run.json "
        "mission_topology; SINGLE skips plan PEER_REVIEW and max_agents lowers dispatch "
        "fan-out (default off)",
    ),
    FlagDef(
        "AGENT_LAB_DRIFT_AUDIT",
        "feature",
        "C2: periodic L3 autonomous-mission plan-vs-execution drift audit -> Inbox proposal (default on)",
        default="1",
    ),
    FlagDef(
        "AGENT_LAB_DRIFT_AUDIT_INTERVAL",
        "feature",
        "C2: human-turn interval between drift audits within an autonomous segment",
        default="10",
    ),
    FlagDef(
        "AGENT_LAB_ORCHESTRATION_DRIFT_RECONCILE",
        "feature",
        "Auto-align plan substate and mission phase when orchestration drift is detected (default on)",
        default="1",
    ),
    FlagDef(
        "AGENT_LAB_ORCHESTRATION_DRIFT_ESCALATE_AFTER",
        "feature",
        "Consecutive unreconciled orchestration drift stamps before Human Inbox escalation",
        default="3",
    ),
    FlagDef(
        "AGENT_LAB_MISSION_BUDGET_USD",
        "feature",
        "Mission cumulative USD ceiling; over → circuit-breaker pause (empty=unlimited)",
    ),
    FlagDef(
        "AGENT_LAB_BUDGET_WARN_PCT",
        "feature",
        "Budget warning threshold percent of MISSION_BUDGET_USD",
        default="80",
    ),
    FlagDef(
        "AGENT_LAB_QUARTER_BUDGET_USD",
        "feature",
        "F8 quarterly USD ceiling across sessions (empty=unlimited)",
    ),
    FlagDef(
        "AGENT_LAB_QUARTER_BUDGET_WARN_PCT",
        "feature",
        "Warn threshold percent of QUARTER_BUDGET_USD",
        default="80",
    ),
    FlagDef(
        "AGENT_LAB_QUARTER_BUDGET_DEMOTE",
        "feature",
        "When quarter budget exceeded, demote autonomy ceiling to L0 (default on if cap set)",
    ),
    FlagDef(
        "AGENT_LAB_RISK_PIN",
        "feature",
        "C3: risk-category topics (trading — F5 lane) pin autonomy ceiling to L1 once per session, via existing N4 demotion inbox (default on)",
        default="1",
    ),
    FlagDef(
        "AGENT_LAB_RULE_SYNC",
        "feature",
        "N10b: propose exporting approved correction rules to .claude/rules, .cursor/rules, ~/.codex/AGENTS.md (default OFF — external blast radius)",
        default="0",
    ),
    FlagDef(
        "AGENT_LAB_CODEX_HOME",
        "infra",
        "Override for the Codex home dir N10b Rule Sync writes AGENTS.md into (default ~/.codex; tests must set this)",
        default="",
    ),
    FlagDef("AGENT_LAB_GOAL_LOOP", "feature", "Session goal Oracle after Room turns"),
    FlagDef("AGENT_LAB_GOAL_ORACLE_LIVE", "feature", "Live Claude oracle for session goal"),
    FlagDef("AGENT_LAB_GOAL_AUTO_CONTINUE", "feature", "One extra discuss round after goal FAIL"),
    FlagDef("AGENT_LAB_ORACLE_LIVE", "feature", "Live Claude oracle for execute verify"),
    FlagDef(
        "AGENT_LAB_ORACLE_MODEL",
        "feature",
        "Claude model id for live execute oracle (empty = CLAUDE_SCRIBE_MODEL)",
    ),
    FlagDef(
        "AGENT_LAB_GOAL_ORACLE_MODEL",
        "feature",
        "Claude model id for live goal oracle (empty = ORACLE_MODEL / scribe default)",
    ),
    FlagDef(
        "AGENT_LAB_PLAN_COLD_CRITIC",
        "feature",
        "Fresh-eyes cold plan critic in PEER_REVIEW (supervisor preset default-on)",
    ),
    FlagDef(
        "AGENT_LAB_MAX_PEER_REVIEW_ROUNDS",
        "feature",
        "Plan peer-review ITERATE cap (default 2)",
        default="2",
    ),
    FlagDef(
        "SUPERVISOR_DELEGATOR",
        "feature",
        "Supervisor preset delegator seat agent id (default codex)",
        default="codex",
    ),
    FlagDef(
        "AGENT_LAB_DIFF_SAFETY",
        "feature",
        "Pre-merge diff secret/danger scanner (gates merge on findings)",
        default="1",
    ),
    FlagDef(
        "AGENT_LAB_TRACE",
        "feature",
        "OTel-lite span tracer → trace.jsonl (turn/agent/tool latency + tokens)",
        default="1",
    ),
    FlagDef(
        "AGENT_LAB_CRASH_RECOVERY",
        "feature",
        "Boot-time reconcile of crashed in-flight merges (G3)",
        default="1",
    ),
    FlagDef(
        "AGENT_LAB_JUDGE_LIVE",
        "feature",
        "Live LLM-as-judge quality eval in score_session (default off)",
    ),
    FlagDef(
        "AGENT_LAB_JUDGE_MODEL",
        "feature",
        "Override Claude model for the quality judge (default scribe model)",
    ),
    FlagDef("AGENT_LAB_ADVERSARIAL_LIVE", "feature", "Live Claude adversarial dry-run note"),
    FlagDef("AGENT_LAB_WISDOM_INDEX", "feature", "Force wisdom index (MB-10)"),
    FlagDef("AGENT_LAB_WISDOM_CROSS_SESSION", "feature", "Cross-session wisdom search"),
    FlagDef("AGENT_LAB_CODEX_PROXY", "feature", "Route Codex via openai-oauth proxy (MB-11)"),
    FlagDef("AGENT_LAB_EXTERNAL_TOOLS", "feature", "Slash external tools from ~/.agent-lab/tools.yaml"),
    FlagDef(
        "AGENT_LAB_EXTERNAL_TOOL_TIMEOUT",
        "feature",
        "External tool subprocess timeout (seconds)",
        default="120",
    ),
    FlagDef("AGENT_LAB_EXECUTE_INBOX", "feature", "Cursor execute inbox MCP", default="1"),
    FlagDef("AGENT_LAB_INBOX_MODE", "feature", "Inbox harvest: sync | soft", default="sync"),
    FlagDef(
        "AGENT_LAB_ORCHESTRATOR_INBOX_HARVEST",
        "feature",
        "Post-turn orchestrator harvest → Inbox (0=MCP-first default)",
        default="0",
    ),
    FlagDef(
        "AGENT_LAB_GATE_SCOPE",
        "feature",
        "Lane-aware gate_scope for discuss pause (1=on, 0=legacy INBOX_MODE only)",
        default="1",
    ),
    FlagDef(
        "AGENT_LAB_SKILL_DRAFTS",
        "feature",
        "Verify PASS → skill draft inbox + session skills (1=on)",
        default="1",
    ),
    FlagDef("AGENT_LAB_ROUTES_CONFIG", "infra", "Path to gateway routes.toml", default=""),
    FlagDef(
        "AGENT_LAB_INBOX_TIMEOUT_SEC",
        "feature",
        "Human inbox wait timeout (seconds)",
        default="1800",
    ),
    FlagDef("AGENT_LAB_INBOX_POLL_SEC", "feature", "Inbox poll interval (seconds)", default="0.25"),
    FlagDef("AGENT_LAB_FACILITATOR_LIVE", "feature", "Live Claude inbox facilitator synthesis"),
    # --- feature: room / context ---
    FlagDef(
        "AGENT_LAB_CODE_MEMORY_MCP",
        "feature",
        "§5 Phase 0 code-memory MCP pilot (local, read-only, manual; default off)",
    ),
    FlagDef(
        "AGENT_LAB_CODE_MEMORY_MODE",
        "feature",
        "Code-memory mode: mock | index (default mock when enabled)",
        default="mock",
    ),
    FlagDef(
        "AGENT_LAB_AUTO_APPROVE_THRESHOLD",
        "feature",
        "Trust-gated auto-approval max risk tier: low | medium (disabled if unset)",
    ),
    FlagDef(
        "AGENT_LAB_AUTO_APPROVE_TIMEOUT_SEC",
        "feature",
        "Human override window before auto-approval fires (default 30s; 0=immediate)",
        default="30",
    ),
    FlagDef(
        "AGENT_LAB_WISDOM_MCP",
        "feature",
        "§5 Phase 1 cross-session Wisdom Index MCP (read+write, default off)",
    ),
    FlagDef(
        "AGENT_LAB_WISDOM_PATH",
        "feature",
        "Override path to wisdom.jsonl (default .agent-lab/wisdom.jsonl)",
    ),
    FlagDef(
        "AGENT_LAB_ROOM_PRESET",
        "feature",
        "Default Room Preset (fast|supervisor)",
    ),
    FlagDef(
        "AGENT_LAB_RUN_PROFILE",
        "feature",
        "Operational profile that sets flag defaults (fast|balanced|thorough|autonomous)",
    ),
    FlagDef("AGENT_LAB_CLARIFIER", "feature", "Short-topic clarifier SSE before agents"),
    FlagDef("AGENT_LAB_CLARIFIER_INTERVIEW", "feature", "Multi-turn clarifier interview mode"),
    FlagDef("AGENT_LAB_CLARIFIER_MIN_CHARS", "feature", "Clarifier topic length threshold", default="48"),
    FlagDef("AGENT_LAB_EFFICIENCY", "feature", "Default efficiency mode for all room calls"),
    FlagDef("AGENT_LAB_R15", "feature", "R1 summary bridge before round 2+"),
    FlagDef("AGENT_LAB_AUTO_PLAN_SCRIBE", "feature", "Re-scribe plan.md after every turn", default="1"),
    FlagDef(
        "AGENT_LAB_TURN_POLICY",
        "feature",
        "Signal-driven TurnPolicy (Scribe/FSM/tasks); replaces Plan toggle",
        default="1",
    ),
    FlagDef(
        "AGENT_LAB_PLAN_WORKFLOW",
        "feature",
        "In-session plan FSM (clarify → peer review → Human approve); =0 disables",
        default="1",
    ),
    FlagDef(
        "AGENT_LAB_PLAN_INBOX",
        "feature",
        "Plan workflow Human Inbox bridge for clarifier / build prompts",
    ),
    FlagDef(
        "AGENT_LAB_PIPELINE",
        "feature",
        "Slash /pipeline handler for mission lifecycle phases",
    ),
    FlagDef(
        "AGENT_LAB_DYNAMIC_ROOM",
        "feature",
        "Dynamic agent roster + provider substitution",
    ),
    FlagDef(
        "AGENT_LAB_DISPATCH_MAX_FANOUT",
        "feature",
        "Cap parallel dispatch fan-out per turn",
        default="3",
    ),
    FlagDef(
        "AGENT_LAB_COMMS_COMPACT",
        "feature",
        "Token compaction for peer digest / multi-agent comms",
    ),
    FlagDef(
        "AGENT_LAB_CLARITY_THRESHOLD",
        "feature",
        "Mission clarity score threshold 0..1 for plan gate",
    ),
    FlagDef(
        "AGENT_LAB_CLARITY_TOPOLOGY",
        "feature",
        "Component-level clarity decomposition (default off)",
    ),
    FlagDef(
        "AGENT_LAB_ROOM_ROLES",
        "feature",
        "Role orchestration personas (proposer/critic/synthesizer); =0 disables",
        default="1",
    ),
    FlagDef(
        "AGENT_LAB_ROOM_MODELS",
        "feature",
        "Session-scoped model roster override via /model slash",
    ),
    FlagDef(
        "AGENT_LAB_ROOM_SUBSTITUTION",
        "feature",
        "Provider substitution when primary agent unavailable",
    ),
    FlagDef(
        "AGENT_LAB_SESSION_TOKEN_BUDGET",
        "feature",
        "Per-session token budget cap for cost demotion",
    ),
    FlagDef(
        "AGENT_LAB_SESSION_HARD_CAP",
        "feature",
        "Hard stop when session token budget exceeded",
    ),
    FlagDef(
        "AGENT_LAB_RUN_LOCK_BACKEND",
        "infra",
        "Run lock backend (file|redis); default file",
        default="file",
    ),
    FlagDef(
        "AGENT_LAB_PIPELINE_PYTHON",
        "feature",
        "Python executable for /pipeline subprocess hooks",
    ),
    FlagDef(
        "AGENT_LAB_INBOX_CALLER_AGENT",
        "feature",
        "Default agent id for MCP inbox caller attribution",
    ),
    FlagDef(
        "AGENT_LAB_INBOX_POLICY_LANE",
        "feature",
        "Inbox policy lane override for harvest routing",
    ),
    FlagDef(
        "AGENT_LAB_SESSION_METRICS_MCP",
        "feature",
        "Read-only session_metrics MCP for Room agents (S1 self-observation)",
        default="1",
    ),
    FlagDef("AGENT_LAB_F2_ARTIFACT_ONLY", "feature", "Specialist R2 artifact-only context", default="1"),
    FlagDef("AGENT_LAB_RECENT_TURNS", "feature", "Recent turns in agent payload", default="8"),
    FlagDef("AGENT_LAB_MAX_THREAD_CHARS", "feature", "Max numbered thread chars", default="96000"),
    FlagDef("AGENT_LAB_NUMBERED_CONTEXT", "feature", "L{n} line refs in agent context", default="1"),
    FlagDef("AGENT_LAB_CONTEXT_WARN_PCT", "feature", "Trim warn budget %", default="75"),
    FlagDef("AGENT_LAB_CONTEXT_CRITICAL_PCT", "feature", "Trim critical budget %", default="90"),
    FlagDef("AGENT_LAB_MAX_AGREED_ITEMS", "feature", "Max agreed items in bundle", default="12"),
    FlagDef("AGENT_LAB_MAX_OPEN_ITEMS", "feature", "Max open items in bundle", default="14"),
    FlagDef("AGENT_LAB_MAX_GATE_LINES", "feature", "Max gate lines in bundle", default="12"),
    FlagDef("AGENT_LAB_MAX_STATUS_TAGS", "feature", "Max status tags in bundle", default="16"),
    FlagDef("AGENT_LAB_MAX_CONSENSUS_ROUNDS", "feature", "Free discuss consensus round cap", default="12"),
    FlagDef("AGENT_LAB_MAX_CONSENSUS_CALLS", "feature", "Free discuss LLM call cap per human turn", default="30"),
    FlagDef("AGENT_LAB_DEBATE_ROUNDS", "feature", "Debate loop rounds before endorse", default="4"),
    FlagDef("AGENT_LAB_MAX_TASKS_PER_TURN", "feature", "Max plan tasks surfaced per turn", default="8"),
    FlagDef(
        "AGENT_LAB_PROPOSED_SKILL_INTENT_THRESHOLD",
        "config",
        "TurnPolicy: [PROPOSED:] count in a turn that opens skill_intent scribe",
        default="3",
    ),
    FlagDef(
        "AGENT_LAB_PLAN_FSM_SKILL_FIRST",
        "feature",
        "P3: plan FSM phase/clarity via MCP first; server tick hold + cap fallback",
        default="1",
    ),
    FlagDef("AGENT_LAB_SCRIBE_RECENT_TURNS", "feature", "Scribe numbered thread trim", default="12"),
    FlagDef("AGENT_LAB_SCRIBE_MAX_CHARS", "feature", "Scribe thread char cap", default="120000"),
    FlagDef("AGENT_LAB_SCRIBE_FULL", "feature", "Full chat.jsonl for scribe"),
    FlagDef("AGENT_LAB_EFFICIENCY_RECENT_TURNS", "feature", "Efficiency recent turns", default="4"),
    FlagDef("AGENT_LAB_EFFICIENCY_MAX_PIN_MSGS", "feature", "Efficiency pin message cap", default="8"),
    FlagDef(
        "AGENT_LAB_EFFICIENCY_PIN_BUDGET_PCT",
        "feature",
        "Efficiency pin budget %",
        default="50",
    ),
    FlagDef("AGENT_LAB_EFFICIENCY_MAX_AGREED", "feature", "Efficiency max agreed items", default="6"),
    FlagDef("AGENT_LAB_EFFICIENCY_MAX_OPEN", "feature", "Efficiency max open items", default="6"),
    FlagDef("AGENT_LAB_EFFICIENCY_REPLY_HINT", "feature", "Efficiency reply char hint", default="800"),
    FlagDef(
        "AGENT_LAB_EFFICIENCY_CONSENSUS_ROUNDS",
        "feature",
        "Efficiency consensus round cap",
        default="8",
    ),
    FlagDef(
        "AGENT_LAB_EFFICIENCY_CONSENSUS_CALLS",
        "feature",
        "Efficiency consensus call cap",
        default="20",
    ),
    FlagDef(
        "AGENT_LAB_EFFICIENCY_DEBATE_ROUNDS",
        "feature",
        "Efficiency debate rounds",
        default="2",
    ),
    # --- feature: hooks / envelope ---
    FlagDef(
        "AGENT_LAB_ENVELOPE_STRICT",
        "feature",
        "Envelope strictness: off | consensus_only | always",
        default="consensus_only",
    ),
    FlagDef("AGENT_LAB_LEGACY_ENDORSE", "feature", "Phrase fallback 「이의 없습니다」"),
    FlagDef(
        "AGENT_LAB_GUIDANCE_TIER",
        "feature",
        "Envelope block size: minimal | standard | debug",
        default="standard",
    ),
    FlagDef("AGENT_LAB_STRUCTURED_ENVELOPE", "feature", "Adapter JSON envelope prefix", default="1"),
    FlagDef("AGENT_LAB_TOPIC_ROUTER", "feature", "Topic category routing (quick/standard/deep/critical)", default="1"),
    FlagDef(
        "AGENT_LAB_DISCUSS_OBJECTIONS", "feature", "Harvest discuss-mode CHALLENGE/BLOCK into objections", default="1"
    ),
    FlagDef(
        "AGENT_LAB_WISDOM_IN_CONTEXT", "feature", "Wisdom hits in R1 context: auto (route) | 0 | 1", default="auto"
    ),
    FlagDef("AGENT_LAB_AGENT_LEARNINGS", "feature", "Harvest [LEARNED:] markers into learnings.md", default="1"),
    FlagDef(
        "AGENT_LAB_TURN_METRICS",
        "feature",
        "S1 Phase A: persist per-turn turn_metrics (roles/oracle/objection rollup) into run.json (default off)",
    ),
    FlagDef(
        "AGENT_LAB_OUTCOME_LEDGER",
        "feature",
        "S1 Phase A: append per-turn outcome rows to .agent-lab/outcomes.jsonl for session-to-session learning (default off)",
    ),
    FlagDef(
        "AGENT_LAB_DOGFOOD_EXECUTE_OUTCOMES",
        "feature",
        "Dogfood suite: record mock execute-phase outcome rows without live Oracle (default off)",
    ),
    FlagDef(
        "AGENT_LAB_CHALLENGE_PRECISION",
        "feature",
        "S1 D1: per-agent CHALLENGE/NOTE tally + adoption rate (challenger-authored-anchor) "
        "in turn_metrics/outcome ledger — record only, not yet consumed by feedback_advisor "
        "(docs/S1-CHALLENGE-PRECISION.md, default off)",
    ),
    FlagDef(
        "AGENT_LAB_WEAKNESS_MINER",
        "feature",
        "HSIL HS1 MINE: per-turn traces (.agent-lab/traces/) + failure_tags memory_store preservation "
        "+ weakness-pattern recurrence mining (default off)",
    ),
    FlagDef(
        "AGENT_LAB_PLAYBOOK",
        "feature",
        "HSIL HS2 PLAYBOOK: incremental knowledge bullets from approved correction rules, "
        "injected into R1 context (default off)",
    ),
    FlagDef(
        "AGENT_LAB_PLAYBOOK_PATH",
        "feature",
        "Override path to playbook.jsonl (default .agent-lab/wisdom/playbook.jsonl)",
    ),
    FlagDef(
        "AGENT_LAB_HARNESS_PROPOSER",
        "feature",
        "HSIL HS3 PROPOSE: bounded PatchCandidate validation (STOP guard/tier/axis/eval-surface gates) "
        "against .agent-lab/harness/manifest.json — offline CLI (scripts/propose_harness.py), no LLM call "
        "(default off)",
    ),
    FlagDef(
        "AGENT_LAB_REGRESSION_GATE",
        "feature",
        "HSIL HS4 REGRESS: worktree apply + declared assertions (HS4-1) + held-out test-fast (HS4-3) + "
        "smoke signal (HS4-4) — offline CLI (scripts/regress_harness.py), verdict decided by assertions "
        "not pass-rate (default off)",
    ),
    FlagDef(
        "AGENT_LAB_HARNESS_INBOX",
        "feature",
        "HSIL HS5 MERGE: harness_patch Human Inbox card -> real git apply+commit for a passing "
        "regression candidate, with rollback+playbook-quarantine (HS5-7) — offline CLI "
        "(scripts/merge_harness.py) (default off)",
    ),
    FlagDef(
        "AGENT_LAB_FEEDBACK_ADVISOR",
        "feature",
        "S1 Phase B: feedback advisor reads outcomes.jsonl and adjusts role/agent setup via SetupHint (default off; requires TURN_METRICS+OUTCOME_LEDGER)",
    ),
    FlagDef(
        "AGENT_LAB_FEEDBACK_MIN_SAMPLE",
        "feature",
        "S1 Phase B: minimum prior outcomes required before advisor applies overrides (default 3)",
        default="3",
    ),
    FlagDef(
        "AGENT_LAB_FEEDBACK_EXPLORE_RATE",
        "feature",
        "S1.5: advisor ε-greedy exploration rate [0,1] — fraction of advised turns that try a non-best/novel role combo (default 0 = pure exploitation, OFF-parity)",
        default="0",
    ),
    FlagDef(
        "AGENT_LAB_TURN_CONTRACT_MODE",
        "feature",
        "TurnContract rollout: off | shadow | roles | adaptive (default shadow)",
        default="shadow",
    ),
    FlagDef(
        "AGENT_LAB_OUTCOMES_ROOT",
        "feature",
        "S1.5: override project root for .agent-lab/outcomes.jsonl (used by dogfood accumulation to isolate the ledger; unset = project root)",
    ),
    FlagDef(
        "AGENT_LAB_CORRECTION_HARVESTER",
        "feature",
        "N10a: harvest user-turn corrections into outcomes.jsonl (user_correction phase); recurring pattern (>=MIN_SAMPLE sessions) proposes a Human Inbox rule candidate (default on)",
        default="1",
    ),
    FlagDef("AGENT_LAB_NATIVE_HOOKS", "feature", "Stage session agent-hooks into workspace cwd"),
    FlagDef("AGENT_LAB_HOOK_TIMEOUT_S", "feature", "Room hook subprocess timeout (seconds)", default="30"),
    # --- feature: resilience ---
    FlagDef("AGENT_LAB_CLI_RETRY_MAX", "feature", "CLI transport retry count", default="3"),
    FlagDef("AGENT_LAB_CLI_RETRY_BASE_SEC", "feature", "CLI retry base delay (seconds)", default="2.0"),
    FlagDef("AGENT_LAB_CLI_RETRY_ROOM_ONLY", "feature", "Limit CLI retries to room turns only"),
    FlagDef(
        "AGENT_LAB_ROOM_SERVER_TIMEOUT_SEC",
        "feature",
        "Server-side Room turn wall-clock timeout in seconds; <=0 disables partial timeout cancellation",
        default="0",
    ),
    FlagDef(
        "AGENT_LAB_SKIP_AUTH_BOOTSTRAP",
        "feature",
        "Skip startup OAuth/API-key sync (Codex/Claude/Cursor)",
    ),
    FlagDef(
        "AGENT_LAB_CLAUDE_HEADLESS_PROBE",
        "feature",
        "Run claude -p auth probe in preflight (slower; default off)",
    ),
    # --- test / dev ---
    FlagDef("AGENT_LAB_MOCK_AGENTS", "test", "Mock agents, plugins, and CLI subprocesses"),
    FlagDef("AGENT_LAB_KIMI_WORK_MODEL", "feature", "Kimi Work model id override for health label"),
    FlagDef(
        "AGENT_LAB_KIMI_WORK_LOOP_PHASE",
        "feature",
        "Kimi Work Loop gate phase (1=waive inbox, 2=inbox required)",
        default="2",
    ),
    FlagDef(
        "AGENT_LAB_KIMI_WORK_INBOX_BRIDGE",
        "feature",
        "Agent Lab Human Inbox bridge for Kimi Work daimon tool calls",
        default="1",
    ),
    FlagDef(
        "AGENT_LAB_KIMI_WORK_ENVELOPE_STRICT",
        "feature",
        "Fail-closed live envelope probe for kimi_work (supports_json_envelope=False on fail)",
        default="0",
    ),
    FlagDef(
        "AGENT_LAB_KIMI_WORK_PROBE_TTL_S",
        "feature",
        "Seconds to trust recent Kimi Work bridge probe (skip repeat WS on health)",
        default="60",
    ),
    FlagDef(
        "AGENT_LAB_KIMI_WORK_WARM_ON_STARTUP",
        "feature",
        "Background daimon warm on API startup (faster first Kimi Work turn)",
        default="1",
    ),
    FlagDef(
        "AGENT_LAB_MODEL_CATALOG_REFRESH",
        "feature",
        "Background Codex model-catalog refresh on startup and stale reads",
        default="0",
    ),
    FlagDef(
        "AGENT_LAB_MODEL_CATALOG_REFRESH_CODEX",
        "feature",
        "When catalog refresh is on, fetch Codex models via OAuth backend",
        default="1",
    ),
    FlagDef(
        "AGENT_LAB_MODEL_CATALOG_TTL_S",
        "feature",
        "Runtime model catalog cache TTL (seconds)",
        default="86400",
    ),
    FlagDef(
        "AGENT_LAB_KIMI_WORK_KEEP_DAIMON_ON_SHUTDOWN",
        "feature",
        "Leave headless daimon running when API stops (faster reopen)",
        default="1",
    ),
    FlagDef(
        "AGENT_LAB_QUIET_ACCESS_LOG",
        "feature",
        "Suppress uvicorn access lines in dev (default on); set 0 to see every GET/POST",
        default="1",
    ),
    FlagDef("KIMI_SHARE_DIR", "infra", "Kimi daimon-share directory override", mask_value=True),
    FlagDef("AGENT_LAB_MOCK_STRUCTURED_ENVELOPE", "test", "Mock structured envelope adapter output"),
    FlagDef("AGENT_LAB_MOCK_ACT_SCRIPT", "test", "Scripted mock envelope acts (JSON path)", mask_value=True),
    FlagDef("AGENT_LAB_RUN_LIVE", "test", "Enable pytest -m live suites"),
    FlagDef("AGENT_LAB_EMERGENCE_BENCH_LIVE", "test", "Allow live emergence bench (CI 금지)"),
    FlagDef("AGENT_LAB_SKIP_LIVE", "test", "Skip live execute spike paths"),
    FlagDef("AGENT_LAB_TAURI_UI_SMOKE_LAUNCH_ONLY", "test", "Tauri UI smoke: launch-only mode"),
    FlagDef("AGENT_LAB_INBOX_POLICY_LANE", "feature", "Inbox policy lane override for harvest routing"),
    # --- F10 burn-down: mission scheduler / offline lane ---
    FlagDef("AGENT_LAB_MISSION_SCHEDULER", "feature", "Background mission scheduler thread (CLI --scheduler)"),
    FlagDef(
        "AGENT_LAB_MISSION_SCHEDULER_INTERVAL_S",
        "feature",
        "Mission scheduler poll interval seconds",
        default="60",
    ),
    FlagDef(
        "AGENT_LAB_ACTIVITY_QUEUE_RECOVERY",
        "feature",
        "Startup and periodic ActivityQueue crash recovery scan (default on; opt out via =0)",
        default="1",
    ),
    FlagDef(
        "AGENT_LAB_ACTIVITY_RECOVERY_INTERVAL_S",
        "feature",
        "Minimum seconds between periodic ActivityQueue recovery scans (default 300; clamped 30..3600)",
        default="300",
    ),
    FlagDef(
        "AGENT_LAB_OFFLINE_ACTIVE_CAP",
        "feature",
        "Max concurrent offline-lane active missions",
    ),
    FlagDef(
        "AGENT_LAB_OFFLINE_WATCH_CAP",
        "feature",
        "Max offline watchlist symbols (trading extension)",
        default="12",
    ),
    FlagDef(
        "AGENT_LAB_RESEARCH_MCP_CRITIC_LIVE",
        "feature",
        "Live LLM for research MCP critic (default mock)",
    ),
    # --- F10 burn-down: infra / daemon ---
    FlagDef("AGENT_LAB_BACKOFF_BASE_SEC", "infra", "Exponential backoff base seconds for retries"),
    FlagDef("AGENT_LAB_CLAUDE_PROBE_TIMEOUT_SEC", "infra", "Claude headless probe timeout seconds"),
    FlagDef(
        "AGENT_LAB_CLAUDE_SKIP_HEADLESS_PROBE",
        "infra",
        "Skip Claude headless capability probe",
    ),
    FlagDef("AGENT_LAB_CODE_MEMORY_ROOT", "infra", "Code-memory MCP root override", mask_value=True),
    FlagDef("AGENT_LAB_DAEMON_STALE_S", "infra", "Mission OS daemon stale threshold seconds"),
    FlagDef("AGENT_LAB_DAEMON_STATE", "infra", "Daemon state file path", mask_value=True),
    FlagDef("AGENT_LAB_FRESHNESS_PYTHON", "infra", "Python executable for freshness probes"),
    FlagDef("AGENT_LAB_GATEWAY_CONFIG", "infra", "Mission gateway config path", mask_value=True),
    FlagDef("AGENT_LAB_KIMI_ENDPOINT", "infra", "Kimi API endpoint override"),
    FlagDef("AGENT_LAB_KIMI_MODEL", "infra", "Kimi model id override"),
    FlagDef("AGENT_LAB_LOCAL_ENDPOINT", "infra", "Local model endpoint override"),
    FlagDef("AGENT_LAB_LOCAL_MODEL", "infra", "Local model id override"),
    FlagDef("AGENT_LAB_OFFLINE_LANE_STATE", "infra", "Offline lane persisted state path", mask_value=True),
    FlagDef("AGENT_LAB_SANDBOX_IMAGE", "infra", "Docker sandbox image when AGENT_LAB_SANDBOX_RUNTIME=docker"),
    FlagDef("AGENT_LAB_SCHEDULER_HOOK_TOKEN", "infra", "Shared secret for scheduler hook auth"),
    FlagDef("AGENT_LAB_SESSION_WORKSPACE", "infra", "Session workspace root override", mask_value=True),
    # --- F10 burn-down: test / mock ---
    FlagDef("AGENT_LAB_AUTH_MOCK_DELAY_S", "test", "Auth mock delay seconds for tests"),
    FlagDef("AGENT_LAB_AUTH_MOCK_RESULT", "test", "Auth mock result override for tests"),
    FlagDef("AGENT_LAB_LOOP_PROBE_LIVE", "test", "Live loop probe (CI forbidden)"),
    # --- F10 / F5 extension lane (trading + quant; internal — not core profile defaults) ---
    FlagDef("AGENT_LAB_ALLOW_BACKTEST_RUN", "internal", "Extension: allow backtest execution"),
    FlagDef("AGENT_LAB_BACKTEST_TIMEOUT_SEC", "internal", "Extension: backtest subprocess timeout"),
    FlagDef("AGENT_LAB_QUOTE_MODE", "internal", "Extension: quote provider mock|kis"),
    FlagDef("AGENT_LAB_TRADING_AGENT_CALLS_CAP", "internal", "Extension: trading agent calls cap"),
    FlagDef("AGENT_LAB_TRADING_DELTA_MAX_PROPOSALS", "internal", "Extension: max delta proposals per cycle"),
    FlagDef("AGENT_LAB_TRADING_DISCUSS_ROUNDS", "internal", "Extension: trading discuss rounds"),
    FlagDef("AGENT_LAB_TRADING_MAX_PROPOSALS", "internal", "Extension: max trading proposals"),
    FlagDef("AGENT_LAB_TRADING_MISSION", "internal", "Extension: enable trading mission loop"),
    FlagDef("AGENT_LAB_TRADING_MISSION_QUEUE", "internal", "Extension: trading mission queue path"),
    FlagDef("AGENT_LAB_TRADING_PARALLEL_ROUNDS", "internal", "Extension: trading parallel rounds"),
    FlagDef("AGENT_LAB_TRADING_PROPOSAL_RETRIES", "internal", "Extension: trading proposal retries"),
    FlagDef("AGENT_LAB_TRADING_RECENT_TURNS", "internal", "Extension: trading recent turns in context"),
    FlagDef("AGENT_LAB_TRADING_SCHEDULE", "internal", "Extension: trading cron schedule"),
    FlagDef("AGENT_LAB_TRADING_SCHEDULER_STATE", "internal", "Extension: trading scheduler state path"),
    FlagDef("AGENT_LAB_TRADING_WATCHER_COOLDOWN_SEC", "internal", "Extension: trading watcher cooldown"),
    FlagDef("AGENT_LAB_TRADING_WATCHER_STATE", "internal", "Extension: trading watcher state path"),
    # --- internal (set by subprocess / session runtime) ---
    FlagDef("AGENT_LAB_SESSION_FOLDER", "internal", "Active session folder (child env)", mask_value=True),
    FlagDef("AGENT_LAB_SESSION_ID", "internal", "Active session id (child env)"),
    FlagDef("AGENT_LAB_EXTERNAL_TOOL_ARGS", "internal", "External tool argv payload (child env)"),
)

_REGISTRY_BY_NAME = {row.name: row for row in FLAG_REGISTRY}


def _effective_bool(raw: str | None, *, default_on: bool = False) -> str:
    if raw is None or not str(raw).strip():
        return "on" if default_on else "off"
    return "on" if is_truthy(str(raw)) else "off"


def _resolve_row(
    row: FlagDef,
    *,
    membership: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    raw = os.getenv(row.name)
    is_set = raw is not None and str(raw).strip() != ""
    if is_set:
        display = mask_tool_path(raw) if row.mask_value else raw.strip()
    else:
        display = None

    if row.default in {"", "0", "off", "false"} and row.category in {"feature", "test"}:
        effective = _effective_bool(raw, default_on=row.default in {"1", "on", "true"})
    elif not is_set:
        effective = row.default or "(unset)"
    else:
        effective = display or row.default or "(unset)"

    profiles = list((membership or {}).get(row.name) or [])
    return {
        "name": row.name,
        "category": row.category,
        "description": row.description,
        "default": row.default or None,
        "value": display,
        "effective": effective,
        "set": is_set,
        "documented": True,
        "profiles": profiles,
    }


def _undocumented_env_flags() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key, raw in sorted(os.environ.items()):
        if not key.startswith("AGENT_LAB_"):
            continue
        if key in _REGISTRY_BY_NAME:
            continue
        display = mask_tool_path(raw) if "DIR" in key or key.endswith("_ROOT") or "PATH" in key else raw
        rows.append(
            {
                "name": key,
                "category": "undocumented",
                "description": None,
                "default": None,
                "value": display,
                "effective": display,
                "set": bool(str(raw).strip()),
                "documented": False,
            }
        )
    return rows


def build_flags_payload(
    *,
    category: str | None = None,
    profile: str | None = None,
) -> dict[str, Any]:
    """Return active AGENT_LAB_* flags for /api/health/flags and list_flags CLI."""
    from agent_lab.run.profile import (
        default_run_profile,
        flag_profile_membership,
        profile_ids,
        resolve_profile,
    )

    cat = (category or "").strip().lower() or None
    if cat and cat not in {"feature", "infra", "test", "internal", "undocumented"}:
        cat = None

    profile_filter = (profile or "").strip().lower() or None
    if profile_filter and resolve_profile(profile_filter) is None:
        profile_filter = None

    membership = flag_profile_membership()

    flags: list[dict[str, Any]] = []
    for row in FLAG_REGISTRY:
        if cat and row.category != cat:
            continue
        resolved = _resolve_row(row, membership=membership)
        if profile_filter and profile_filter not in resolved["profiles"]:
            continue
        flags.append(resolved)

    undocumented = _undocumented_env_flags()
    if cat in {None, "undocumented"} and profile_filter is None:
        for row in undocumented:
            row = {**row, "profiles": []}
            flags.append(row)

    categories = sorted({row.category for row in FLAG_REGISTRY})
    if undocumented:
        categories.append("undocumented")

    return {
        "ok": True,
        "count": len(flags),
        "registry_count": len(FLAG_REGISTRY),
        "categories": categories,
        "category_filter": cat,
        "profile_filter": profile_filter,
        "active_profile": default_run_profile(),
        "profiles": list(profile_ids()),
        "flags": flags,
        "undocumented_count": len(undocumented),
    }
