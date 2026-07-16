"""Integration module registry — keep slow suites out of make test-fast."""

from __future__ import annotations

import importlib.util
import inspect
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_CONFTEST_PATH = ROOT / "tests" / "conftest.py"
_spec = importlib.util.spec_from_file_location("tests_conftest", _CONFTEST_PATH)
assert _spec and _spec.loader
conftest = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(conftest)


def _resolve_pytest() -> str:
    venv = ROOT / ".venv" / "bin" / "pytest"
    if venv.is_file():
        return str(venv)
    on_path = shutil.which("pytest")
    if on_path:
        return on_path
    raise FileNotFoundError("pytest not found (.venv/bin/pytest or PATH)")


def test_integration_modules_include_profiled_slow_suites():
    """Modules profiled >10s in test-fast (2026-06-14) must stay integration-tagged."""
    required = {
        "test_discuss_objections",
        "test_plan_execute_worktree",
        "test_plan_execute_revise_api",
        "test_plan_execute_agent_repair",
        "test_live_execute_spike",
        "test_dev_preview_api",
        "test_dev_preview_probe",
        "test_human_inbox",
        "test_context_bundle",
        "test_plan_execute",
        "test_recombination",
        "test_topic_router",
    }
    registered = set(conftest._INTEGRATION_MODULES)
    missing = sorted(required - registered)
    assert not missing, f"Add to _INTEGRATION_MODULES: {missing}"


def test_fast_bucket_collection_budget():
    """test-fast should stay a PR-sized subset (integration carries the rest)."""
    proc = subprocess.run(
        [
            _resolve_pytest(),
            "tests/",
            "--collect-only",
            "-q",
            "-m",
            "not live and not integration",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    line = proc.stdout.strip().splitlines()[-1]
    count = int(line.split("/")[0])
    # 2026-06-17: raised 1100 -> 1150 for the divergence / token-efficiency /
    # run-lock-recovery fast unit suites (genuinely fast, belong in the fast lane).
    # 2026-06-18: raised 1150 -> 1200 for the AGENT_LAB_PIPELINE transplant fast unit
    # suites (clarity scorer, mode router, goal ledger, CLARIFY scaffold).
    # 2026-06-18: raised 1200 -> 1300 for the AGENT_LAB_DYNAMIC_ROOM fast unit suites
    # (provider registry, account chain, agent roster, consensus floor, slash commands).
    # 2026-06-19: raised 1300 -> 1320 for kimi_work P3-P4 fast suites (supervisor, session, smoke).
    # 2026-06-19: raised 1320 -> 1340 for AGENT_LAB_COMMS_COMPACT token-compaction suites (pin cap + peer digest).
    # 2026-06-19: raised 1340 -> 1360 for §1 pipeline handles (/pipeline,/clarify,/plan) + CLARIFY transition rows.
    # 2026-06-19: raised 1360 -> 1380 for model-switch safety probe (substitute recognition + 2-stage live capability).
    # 2026-06-20: raised 1380 -> 1400 for §5 Phase 0 code-memory MCP pilot (server + contract + mount + off-parity + cache).
    # 2026-06-21: raised 1400 -> 1430 for CLARIFY unification (clarifier_engine adapter AC1-AC15 suite).
    # 2026-06-22: raised 1430 -> 1560 for stage-aware routing + anti-drift (phase->route resolver, RoutingDecisionLog telemetry, anti-drift A/B + fresh-eyes seat, and adversarial red-team suites).
    # 2026-06-23: raised 1560 -> 1600 for the P0 checkpoint/resume layer (checkpoint_store snapshot/restore + OFF-parity AC1-AC11 suite).
    # 2026-06-23: raised 1600 -> 1640 for the P1 symbol-graph repo-map (repo_map extract/rank/render + OFF-parity AC1-AC10 suite).
    # 2026-06-23: P2 tool-output auto-compaction (test_tool_output_compaction AC1-AC10 + N1/N2) fits under 1640; no bump needed.
    # 2026-06-23: raised 1640 -> 1680 for the P3 edit-time syntax gate + sandbox policy seam (test_syntax_gate AC1-AC6 + test_sandbox_policy AC7-AC12 + OFF-parity/defensive suites).
    # 2026-06-24: P4/P5 fit under 1680 (test_eval_harness/event_schema/memory_store). Raised 1680 -> 1720 for the P4/P5 consumer wiring (test_eval_memory_routes: /api/eval/score + /api/memory/eval + room.py flag-path).
    # 2026-06-25: raised 1720 -> 1800 for room_context + room_turn_flow unit suites (63 tests: is_pass_response, is_no_objection, split_plan_sections, trim/compact/pin helpers, emit_budget_status, stage_routing flag-off parity).
    # 2026-06-26: raised 1800 -> 1810 for S1 Phase A feedback loop suites (test_turn_metrics + test_s1_loop_closure_e2e: turn_metrics rollup, outcome ledger append/flag-gating, loop-closure E2E + OFF-parity).
    # 2026-06-26: raised 1810 -> 1830 for S1 Phase B feedback_advisor suites (test_feedback_advisor: score/filter/combo-selection/flag-gating/available-agent-filter).
    # 2026-06-26: raised 1830 -> 1960 for PR#57 merge — auto_approve_gate, diff_risk, evidence_api, openai_compat, room_preset, run_profile, wisdom_store suites.
    # 2026-06-27: raised 1960 -> 2050 for API bootstrap/smoke + session-scoped cancel + provider contextvars fast suites.
    # 2026-06-27: raised 2050 -> 2060 for DRAFT→PEER_REVIEW auto-advance tests + clarifier harvest fixes.
    # 2026-06-29: raised 2143 -> 2170 for TurnPolicy Wave F (test_turn_policy + UI handoff updates).
    # 2026-06-29: raised 2170 -> 2174 for TurnPolicy C3-C5 regression tests.
    # 2026-06-29: raised 2174 -> 2195 for MCP-first harvest tests, turn_flow split, session metrics MCP.
    # 2026-06-30: raised 2195 -> 2220 for S1 feedback loop waves (objection_resolution rollup,
    # pure_challenge_yield, feedback_report accepted_challenge_rate, run_profile S1 flags).
    # 2026-07-05: raised 2220 -> 2460 for F9 Stage 3 (RoomChat hooks, room facade guard, plan panel support).
    # 2026-07-05: raised 2460 -> 2470 for F11 Stage 1 RunState boundary + F11 ratchet guard.
    # 2026-07-06: raised 2480 -> 2500 for N8 verify (quickstart + emergence reference unit tests).
    # 2026-07-06: raised 2500 -> 2510 for N9 verify API audit headers (test_n9_verify_api.py).
    # 2026-07-06: raised 2510 -> 2550 for eval-surface v1 §1/§2 (feedback_report coverage fields,
    # feedback_advisor execute-preferred fallback, test_eval_surface_export/graders/run_local).
    # 2026-07-06: raised 2550 -> 2570 for N10a correction harvester (test_correction_harvester.py:
    # detection, RECORD, W2 rule-promotion, Human Inbox resolve — 19 fast unit tests).
    # 2026-07-06: raised 2570 -> 2590 for C1 diagnose-before-retry (test_partial_retry.py:
    # failure-signature guard, Inbox escalation/dedup, force + ack bypass — 9 fast unit tests).
    # 2026-07-06: raised 2590 -> 2610 for C2 drift audit (test_drift_audit.py: baseline
    # snapshot, uncovered-action diff, interval-gated escalation, reground resolve — 15 tests).
    # 2026-07-06: raised 2610 -> 2630 for C3 risk-inverse profile pin (test_risk_pin.py:
    # ceiling pin/no-op, demotion-inbox reuse, idempotent Human-override respect — 10 tests).
    # 2026-07-07: raised 2630 -> 2650 for N6 self-patch allowlist infra (test_self_patch.py:
    # allowlist load/glob matching/classify — 14 tests, + 2 outcome_harvester + 2 feedback_report).
    # 2026-07-08: raised 2700 -> 2705 for x2 dogfood fixture config tests.
    # 2026-07-08: raised 2705 -> 2720 for HS0 ATTRIB (eval_harness score_dogfood_status/
    # score_outcome_verdict adapters + harness_failure_rate + feedback_report/dogfood-suite wiring).
    # 2026-07-08: raised 2720 -> 2740 for HS1 MINE (turn_metrics failure_tags taxonomy,
    # weakness_miner.py traces/memory_store/pattern-recurrence tests, execute-outcome tags).
    # 2026-07-08: raised 2740 -> 2760 for HS2 PLAYBOOK (wisdom/playbook.py curator/query tests,
    # correction_harvester dual-write, context bundle playbook block injection).
    # 2026-07-09: raised 2760 -> 2795 for HS3 PROPOSE (harness_proposer.py manifest/tier/axis/
    # STOP-guard/BLOCK-parser tests, propose_harness.py CLI subprocess tests, self_patch.py
    # allowlist-migration test rewrite).
    # 2026-07-09: raised 2795 -> 2825 for HS4 REGRESS (regression_gate.py held-in/diff-introspection/
    # worktree/assertion tests incl. 2 real-git end-to-end pytest-isolation tests, regress_harness.py
    # CLI subprocess tests).
    # 2026-07-09: raised 2825 -> 2847 for HS5 MERGE (merge_gate.py Inbox gate/commit/rollback/KPI
    # tests, incl. real-git apply+commit+revert end-to-end coverage).
    # 2026-07-09: raised 2847 -> 2852 for HS5-3 (Tier A + L2 lightweight-approval gate:
    # autonomy_promotion.harness_patch_light_approval_eligible + merge_gate wiring tests).
    # 2026-07-09: raised 2852 -> 2853 for HS1-1 false_success on execute rows
    # (derive_execution_failure_tags shared helper — closes the structurally-dead-signal gap).
    # 2026-07-09: raised 2853 -> 2858 for HS0-4 (harness_reproducibility_pp preset
    # A/B swap) + HS4-2 completion (X5/X6 held-in curation topics + _TAG_TOPIC_MAP).
    # 2026-07-09: raised 2858 -> 2890 for env_flags.py (test_env_flags.py) — SSOT for the
    # AGENT_LAB_*/CLAUDE_*/CODEX_* truthy-env-var + optional-int idiom deduped out of
    # ~32 modules incl. claude/cli.py + codex/cli.py's byte-identical helpers.
    # 2026-07-11: raised 2890 -> 2994 for TurnIntent observer extraction
    # (test_turn_contract_runtime.py + expanded test_turn_contract.py/
    # test_turn_policy.py/test_eval_surface_graders.py coverage).
    # 2026-07-11: raised 2994 -> 3024 for dual FSM orchestration + plan_lane tests.
    # 2026-07-12: raised 3024 -> 3029 for dual FSM slice D orchestration tests.
    # 2026-07-12: raised 3029 -> 3039 for plan substate transition table tests.
    # 2026-07-12: raised 3039 -> 3046 for orchestration drift auto-reconcile tests.
    # 2026-07-12: raised 3046 -> 3050 for orchestration work_phase unify tests.
    # 2026-07-14/15: raised 3050 -> 3311 for Wave A/B Mission kernel + dual-write + journal-first
    # read-model + §7.4 SSE cursor wiring (~30 new modules: test_mission_kernel/journal/repository/
    # lease/messages/projection/scheduler_shadow, dual_write + dual_read variants, activity_queue/
    # activity_runtime, decision_queue, m6_* retire/consumer-inventory gates, mission_read_model +
    # mission_read_model_wave_b/api, mission_events_sse, context_recipe, local_dispatcher,
    # multi_agent_topology, human_resume_bridge).
    # 2026-07-15: raised 3311 -> 3316 for §7.3 Human Inbox answer optimistic locking
    # (guard_inbox_answer/load_decision_version tests in test_mission_application.py,
    # stale-expected_version HTTP conflict tests in test_human_inbox.py,
    # decision_version read-model coverage in test_mission_read_model_api.py).
    # 2026-07-16: raised 3316 -> 3319 for sector 02 claim-lease merge guard
    # (test_resolve_approve_rejects_when_merge_lease_already_held in
    # test_plan_execute_worktree.py) + sector 08 CM1 message inventory drift
    # guard (test_message_inventory.py).
    # 2026-07-16: raised 3319 -> 3321 for sector 09 CX1 source registry drift
    # guard (test_context_source_registry.py).
    # 2026-07-16: raised 3321 -> 3324 for sector 03 A1 provider capability
    # inventory drift guard (test_provider_capability_inventory.py).
    # 2026-07-16: raised 3324 -> 3326 for sector 05 R1 journey reliability
    # matrix drift guard (test_regression_journey_matrix.py).
    # 2026-07-16: raised 3326 -> 3329 for sector 05 R2 cancel-journey first
    # slice (test_execute_cancel.py).
    # 2026-07-16: raised 3329 -> 3331 for sector 03 A1 cancel/resume correction
    # tests (test_provider_capability_inventory.py).
    # 2026-07-16: raised 3331 -> 3346 for sector 09 CX2 activity recipe schema
    # tests (test_activity_recipes.py).
    # 2026-07-16: raised 3346 -> 3354 for sector 09 CX3 provenance/freshness/
    # security + redaction tests (test_context_manifest_cx3.py).
    # 2026-07-16: raised 3354 -> 3359 for sector 09 CX4 deterministic selector
    # tests (test_context_selector_cx4.py).
    # 2026-07-16: raised 3359 -> 3366 for the CX1-CX4 Human review pass (REPO_CONTEXT
    # tier fix, SYSTEM_INVARIANT gap fix, pii redaction policy fix, budget review).
    # 2026-07-16: raised 3366 -> 3371 for the select_context() code-review fixes
    # (test_context_selector_review2.py — required-source/conflict-key/freshness/
    # cross-source-dedup bugs).
    # 2026-07-16: raised 3371 -> 3390 for the round-3 construction-time validation
    # fixes (test_context_selector_review3.py — security_label/empty-key/empty-
    # content/ContextNeed-overlap/trusted-default).
    # 2026-07-16: raised 3390 -> 3401 for the round-4 conflict-resolution fixes
    # (test_context_selector_review4.py — genuine-tie escalation to
    # unresolved_conflicts, conflict_key-vs-content dedup ordering, excluded/
    # superseded reason/winner tracking, duplicate item_id rejection).
    # 2026-07-16: raised 3401 -> 3408 for the round-5 conflict-resolution
    # fixes (test_context_selector_review4.py required-source-unresolved-tie
    # hard fail + regression guards; test_context_selector_review5.py —
    # non-transitive core-comparator fix, partition invariant, redacted
    # content-floor exemption).
    # 2026-07-16: raised 3408 -> 3424 for the CX1 producer->ContextItem
    # adapter (context/adapters.py + test_context_adapters.py, 16 tests) —
    # the first thing that actually feeds select_context() from real
    # producer output instead of only synthetic ContextItems.
    # 2026-07-16: raised 3424 -> 3435 for §7.2 trim steps 3-6
    # (context/compress.py + test_context_compress.py, 11 tests) —
    # tool-output-to-artifact-ref, transcript/required-item structured
    # summary, repo-tree-to-symbol-snippets, wired around select_context()
    # via trim_to_budget().
    # 2026-07-16: raised 3435 -> 3459 for the CX8 flag-gated shadow slice
    # (adapt_approved_plan + 2 tests; context/bundle_recipe.py +
    # test_context_bundle_recipe.py, 22 tests) — NOT wired into
    # build_context_bundle's live path; a standalone, independently-callable
    # first step toward CX8 convergence, gated by AGENT_LAB_CONTEXT_RECIPE.
    assert count <= 3459, f"test-fast bucket grew to {count}; mark slow modules integration"


def test_integration_registry_is_frozen_set():
    src = inspect.getsource(conftest)
    assert "_INTEGRATION_MODULES = frozenset(" in src
