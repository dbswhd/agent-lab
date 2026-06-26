"""External refs plan traceability — doc and evidence paths stay aligned."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRACEABILITY = ROOT / "docs" / "EXTERNAL-REFS-TRACEABILITY.md"
PLAN = ROOT / "docs" / "archive" / "rfcs" / "EXTERNAL-REFS-PLAN.md"

SHIPPED_ROWS: list[tuple[str, list[str]]] = [
    ("L1", ["src/agent_lab/cli_retry.py"]),
    ("L2", ["src/agent_lab/room_consensus.py"]),
    ("LC-oracle", ["tests/test_oracle_verify.py", "src/agent_lab/plan_execute_merge.py"]),
    (
        "LC-L3",
        [
            "sessions/_regression/execute_verify_loop",
            "tests/test_plan_execute_agent_repair.py",
            "tests/test_plan_execute_reverify_api.py",
        ],
    ),
    ("CENT-durable", ["tests/test_durable_completed_steps.py", "sessions/_regression/durable_completed_steps"]),
    (
        "LC-L4",
        [
            "src/agent_lab/adversarial_gate.py",
            "sessions/_regression/adversarial_gate_lgtm",
            "tests/test_lc_l4_runtime.py",
        ],
    ),
    ("LC-L5", ["src/agent_lab/goal_loop.py", "sessions/_regression/goal_loop_achieved", "tests/test_goal_loop.py"]),
    ("MD-PLATFORM", [".agent-lab/PLATFORM.md", "src/agent_lab/platform_md.py", "tests/test_platform_md.py"]),
    ("LC-clarifier", ["src/agent_lab/session_clarifier.py", "tests/test_session_clarifier.py"]),
    ("CC-hooks", [".claude/settings.json", ".claude/hooks/stop-pytest.sh", "tests/test_claude_hooks.py"]),
    ("CC-rules", [".claude/rules/python-backend.md", ".claude/rules/react-frontend.md", "tests/test_claude_rules.py"]),
    (
        "CC-skills",
        [
            ".claude/skills/init-project-memory/SKILL.md",
            "src/agent_lab/project_memory.py",
            "tests/test_project_memory.py",
        ],
    ),
    ("PI", ["src/agent_lab/plan_execute_worktree.py", "sessions/_regression/worktree_merge_ok"]),
    ("CON-diff", ["tests/test_plan_execute_revise_api.py", "web/src/components/PlanExecutePanel.tsx"]),
    ("PI-executed", ["src/agent_lab/plan_execute_merge.py", "tests/test_executed_archive.py"]),
    ("MD-P3", ["src/agent_lab/workspace_md.py", "tests/test_workspace_md.py"]),
    ("PI-ops", ["scripts/live_cursor_worktree_dry_run.py", "docs/OPS-RUNBOOK.md"]),
    ("PI-ops-C", ["scripts/live_cursor_worktree_merge_run.py", "docs/LIVE-MERGE-OPERATOR.md"]),
    ("E-smoke", ["scripts/smoke_room.py", "sessions/_regression/objection_blocks_execute"]),
    (
        "MB-3",
        ["src/agent_lab/evidence_gates.py", "sessions/_regression/evidence_gates_merged_ok"],
    ),
    (
        "MB-4",
        ["src/agent_lab/evidence_ledger.py", "sessions/_regression/evidence_ledger_stream"],
    ),
    (
        "MB-8",
        ["src/agent_lab/external_handoff.py", "sessions/_regression/external_handoff_attached"],
    ),
    (
        "MB-10",
        ["src/agent_lab/wisdom_index.py", "sessions/_regression/wisdom_index_built"],
    ),
    ("F-R3", ["sessions/_benchmark/specialist_asymmetric_cwd"]),
    ("H-P1", ["tests/test_session_score_ci.py"]),
    (
        "H-P2",
        [
            "sessions/_benchmark/README.md",
            "tests/test_benchmark_catalog.py",
            "tests/test_room_delegate_replay.py",
        ],
    ),
    ("H4-weekly", ["scripts/score_sessions_weekly.py"]),
    ("H4-ops-live", ["tests/test_weekly_live_ops_summary.py"]),
    ("ops-P2", ["app/server/routers/health.py"]),
    ("ops-verify", ["Makefile", "docs/OPS-RUNBOOK.md"]),
    (
        "ops-flags",
        [
            "src/agent_lab/runtime_flags.py",
            "scripts/list_flags.py",
            "tests/test_health_flags_api.py",
        ],
    ),
    ("CENT-env", ["src/agent_lab/subprocess_env.py", "tests/test_subprocess_env.py"]),
    (
        "HOOK-COMM",
        [
            "src/agent_lab/reply_policy.py",
            "src/agent_lab/room_hooks.py",
            "docs/HOOK-COMMUNICATE-REFORM.md",
            "Makefile",
        ],
    ),
    (
        "RT-H0",
        [
            "src/agent_lab/runtime/transitions.py",
            "src/agent_lab/runtime/mission_lane.py",
            "tests/test_runtime_transition_table.py",
            "tests/test_runtime_mission_dispatch.py",
            "tests/test_mission_loop_e2e.py",
        ],
    ),
    ("RT-H1", ["src/agent_lab/runtime/snapshot.py", "tests/test_runtime_snapshot.py"]),
    ("RT-H2", ["src/agent_lab/runtime/execute_lane.py", "tests/test_runtime_dispatch.py"]),
    ("RT-H3", ["src/agent_lab/runtime/discuss_lane.py", "tests/test_runtime_discuss_dispatch.py"]),
    ("RT-H4", ["src/agent_lab/runtime/policy.py", "tests/test_runtime_policy.py"]),
    ("RT-H5", ["src/agent_lab/runtime/adapters", "tests/test_runtime_adapters.py"]),
    ("RT-H6", ["src/agent_lab/runtime/boulder.py", "tests/test_runtime_boulder.py"]),
    ("RT-H7", ["src/agent_lab/runtime/external_runner.py", "tests/test_external_runner.py"]),
]

PARTIAL_ROWS: list[tuple[str, list[str]]] = []

FUTURE_TICKETS: tuple[str, ...] = ()

FUTURE_REGRESSION_FOLDERS: tuple[str, ...] = ()

DEV_TOOL_IDS = (
    "CC-CLAUDE",
    "CC-hooks",
    "CC-rules",
    "CC-skills",
    "CON-diff",
    "MD-PLATFORM",
    "MD-PROJECT",
    "MD-P3",
    "PI-executed",
)


def _read(path: Path) -> str:
    assert path.is_file(), f"missing doc: {path}"
    return path.read_text(encoding="utf-8")


def test_traceability_doc_exists_and_links_plan():
    text = _read(TRACEABILITY)
    assert "EXTERNAL-REFS-PLAN.md" in text
    assert "MD-WRITING-PLAN.md" in text
    assert "Status legend" in text or "✅ shipped" in text
    assert "Dev-tool & prompt layer" in text


def test_shipped_rows_have_existing_evidence():
    text = _read(TRACEABILITY)
    for row_id, paths in SHIPPED_ROWS:
        assert row_id in text, f"traceability missing row id {row_id}"
        found = any((ROOT / p).exists() for p in paths)
        assert found, f"{row_id}: none of {paths} exist"


def test_partial_rows_have_existing_evidence():
    text = _read(TRACEABILITY)
    for row_id, paths in PARTIAL_ROWS:
        assert row_id in text, f"traceability missing partial row id {row_id}"
        found = any((ROOT / p).exists() for p in paths)
        assert found, f"{row_id}: none of {paths} exist"


def test_future_fixture_tickets_documented():
    text = _read(TRACEABILITY)
    for ticket in FUTURE_TICKETS:
        assert ticket in text, f"missing future ticket {ticket}"


def test_lc_l3_oracle_dependency_documented():
    text = _read(TRACEABILITY)
    assert "LC-L3" in text and "verify_after_merge()" in text
    assert "oracle_verify()" in text
    assert "/api/sessions/{id}/execute/reverify" in text
    assert "MAX_VERIFY_RETRIES" in text
    assert "Cursor/Codex" in text


def test_cent_durable_shipped_not_future_ticket():
    text = _read(TRACEABILITY)
    assert "CENT-durable" in text
    assert "### Ticket: `durable_completed_steps`" not in text


def test_dev_tool_ids_documented():
    text = _read(TRACEABILITY)
    for dev_id in DEV_TOOL_IDS:
        assert dev_id in text, f"missing dev-tool id {dev_id}"


def test_md_writing_plan_execution_table_shipped():
    from pathlib import Path

    md_plan = Path(__file__).resolve().parents[1] / "docs" / "MD-WRITING-PLAN.md"
    text = md_plan.read_text(encoding="utf-8")
    assert "⬜ 미작성" not in text
    assert "CC-CLAUDE" in text and "✅" in text


def test_plan_has_stale_banner_and_traceability_link():
    text = _read(PLAN)
    assert "EXTERNAL-REFS-TRACEABILITY.md" in text
    assert "Status" in text or "shipped" in text.lower()
    assert "queue is empty" in text.lower() or "empty" in text.lower()
    assert "CENT-env" in text


def test_plan_loop_layers_match_traceability():
    text = _read(PLAN)
    assert "Layer 3: Execute Verify Loop | ✅" in text
    assert "Layer 4: Adversarial Gate | ✅" in text
    assert "Layer 5: Goal-Driven Loop | ✅" in text
    assert "subprocess credential 분리 **✅ shipped**" in text or "✅ shipped" in text


def test_plan_phase_three_ops_marked_shipped_in_traceability():
    text = _read(TRACEABILITY)
    assert "ops-P2" in text
    assert "ops-P0" in text
    assert "H-P1" in text
    assert "H-P2" in text


def test_traceability_cc_claude_cross_ref_not_duplicated_in_shipped_table():
    text = _read(TRACEABILITY)
    assert "CC-CLAUDE" in text
    assert "Dev-tool cross-ref" in text or "§Dev-tool" in text
    shipped_section = text.split("## Dev-tool")[0]
    assert shipped_section.count("| CC-CLAUDE |") == 0


def test_traceability_goal_loop_and_oracle_evidence_documented():
    text = _read(TRACEABILITY)
    assert "GOAL-LOOP.md" in text
    assert "adversarial_gate_lgtm" in text
    assert "AGENT_LAB_ORACLE_LIVE" in text
    assert "per-dir AGENTS hierarchy not implemented" in text or "hierarchical AGENTS" in text


def test_traceability_future_regression_folders_not_present_yet():
    regression = ROOT / "sessions" / "_regression"
    for ticket in FUTURE_REGRESSION_FOLDERS:
        assert not (regression / ticket).is_dir(), f"{ticket} should not exist yet"


def test_durable_completed_steps_fixture_exists():
    fixture = ROOT / "sessions" / "_regression" / "durable_completed_steps"
    assert fixture.is_dir()
    assert (fixture / "run.json").is_file()


def test_adversarial_gate_lgtm_fixture_exists():
    fixture = ROOT / "sessions" / "_regression" / "adversarial_gate_lgtm"
    assert fixture.is_dir()
    assert (fixture / "run.json").is_file()
    assert (fixture / "expected_badges.json").is_file()
