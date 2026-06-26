"""Curated AGENT_LAB_* env flag registry for API/CLI discoverability."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Literal

from agent_lab.api_diagnostics import mask_tool_path

FlagCategory = Literal["feature", "infra", "test", "internal"]

_TRUE = frozenset({"1", "true", "yes", "on"})


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
        "AGENT_LAB_STAGE_ROUTING", "feature", "Phase-aware single-vs-panel routing (stage-aware selective; default off)"
    ),
    FlagDef(
        "AGENT_LAB_ANTIDRIFT",
        "feature",
        "Structural anti-drift defenses for panel turns (state re-injection, unanimity red-team, fresh-eyes critic seat; default off)",
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
    FlagDef("AGENT_LAB_GOAL_LOOP", "feature", "Session goal Oracle after Room turns"),
    FlagDef("AGENT_LAB_GOAL_ORACLE_LIVE", "feature", "Live Claude oracle for session goal"),
    FlagDef("AGENT_LAB_GOAL_AUTO_CONTINUE", "feature", "One extra discuss round after goal FAIL"),
    FlagDef("AGENT_LAB_ORACLE_LIVE", "feature", "Live Claude oracle for execute verify"),
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
    FlagDef("AGENT_LAB_CLARIFIER", "feature", "Short-topic clarifier SSE before agents"),
    FlagDef(
        "AGENT_LAB_CLARIFIER_ENGINE",
        "feature",
        "Back the server clarifier with the clarity scoring engine (default off)",
    ),
    FlagDef("AGENT_LAB_CLARIFIER_INTERVIEW", "feature", "Multi-turn clarifier interview mode"),
    FlagDef("AGENT_LAB_CLARIFIER_MIN_CHARS", "feature", "Clarifier topic length threshold", default="48"),
    FlagDef("AGENT_LAB_EFFICIENCY", "feature", "Default efficiency mode for all room calls"),
    FlagDef("AGENT_LAB_R15", "feature", "R1 summary bridge before round 2+"),
    FlagDef("AGENT_LAB_AUTO_PLAN_SCRIBE", "feature", "Re-scribe plan.md after every turn", default="1"),
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
        "AGENT_LAB_OUTCOMES_ROOT",
        "feature",
        "S1.5: override project root for .agent-lab/outcomes.jsonl (used by dogfood accumulation to isolate the ledger; unset = project root)",
    ),
    FlagDef("AGENT_LAB_NATIVE_HOOKS", "feature", "Stage session agent-hooks into workspace cwd"),
    FlagDef("AGENT_LAB_HOOK_TIMEOUT_S", "feature", "Room hook subprocess timeout (seconds)", default="30"),
    # --- feature: resilience ---
    FlagDef("AGENT_LAB_CLI_RETRY_MAX", "feature", "CLI transport retry count", default="3"),
    FlagDef("AGENT_LAB_CLI_RETRY_BASE_SEC", "feature", "CLI retry base delay (seconds)", default="2.0"),
    FlagDef("AGENT_LAB_CLI_RETRY_ROOM_ONLY", "feature", "Limit CLI retries to room turns only"),
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
    FlagDef("KIMI_SHARE_DIR", "infra", "Kimi daimon-share directory override", mask_value=True),
    FlagDef("AGENT_LAB_MOCK_STRUCTURED_ENVELOPE", "test", "Mock structured envelope adapter output"),
    FlagDef("AGENT_LAB_MOCK_ACT_SCRIPT", "test", "Scripted mock envelope acts (JSON path)", mask_value=True),
    FlagDef("AGENT_LAB_RUN_LIVE", "test", "Enable pytest -m live suites"),
    FlagDef("AGENT_LAB_EMERGENCE_BENCH_LIVE", "test", "Allow live emergence bench (CI 금지)"),
    FlagDef("AGENT_LAB_SKIP_LIVE", "test", "Skip live execute spike paths"),
    FlagDef("AGENT_LAB_TAURI_UI_SMOKE_LAUNCH_ONLY", "test", "Tauri UI smoke: launch-only mode"),
    # --- internal (set by subprocess / session runtime) ---
    FlagDef("AGENT_LAB_SESSION_FOLDER", "internal", "Active session folder (child env)", mask_value=True),
    FlagDef("AGENT_LAB_SESSION_ID", "internal", "Active session id (child env)"),
    FlagDef("AGENT_LAB_EXTERNAL_TOOL_ARGS", "internal", "External tool argv payload (child env)"),
)

_REGISTRY_BY_NAME = {row.name: row for row in FLAG_REGISTRY}


def _effective_bool(raw: str | None, *, default_on: bool = False) -> str:
    if raw is None or not str(raw).strip():
        return "on" if default_on else "off"
    return "on" if str(raw).strip().lower() in _TRUE else "off"


def _resolve_row(row: FlagDef) -> dict[str, Any]:
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

    return {
        "name": row.name,
        "category": row.category,
        "description": row.description,
        "default": row.default or None,
        "value": display,
        "effective": effective,
        "set": is_set,
        "documented": True,
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


def build_flags_payload(*, category: str | None = None) -> dict[str, Any]:
    """Return active AGENT_LAB_* flags for /api/health/flags and list_flags CLI."""
    cat = (category or "").strip().lower() or None
    if cat and cat not in {"feature", "infra", "test", "internal", "undocumented"}:
        cat = None

    flags: list[dict[str, Any]] = []
    for row in FLAG_REGISTRY:
        if cat and row.category != cat:
            continue
        flags.append(_resolve_row(row))

    undocumented = _undocumented_env_flags()
    if cat in {None, "undocumented"}:
        flags.extend(undocumented)

    categories = sorted({row.category for row in FLAG_REGISTRY})
    if undocumented:
        categories.append("undocumented")

    return {
        "ok": True,
        "count": len(flags),
        "registry_count": len(FLAG_REGISTRY),
        "categories": categories,
        "category_filter": cat,
        "flags": flags,
        "undocumented_count": len(undocumented),
    }
