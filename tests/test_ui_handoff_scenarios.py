"""UI-HANDOFF §5 A–E — contract smoke (automated path checks)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web" / "src"


def _read(*parts: str) -> str:
    return ROOT.joinpath(*parts).read_text(encoding="utf-8")


def test_scenario_a_discuss_only_contract():
    """A: discuss mode, receipt, human synthesis, peer channel, claimable."""
    room = _read("web", "src", "components", "RoomChat.tsx")
    composer = _read("web", "src", "components", "ChatComposer.tsx")
    taskbar = _read("web", "src", "components", "RoomTaskBar.tsx")
    receipt = _read("web", "src", "utils", "sendReceipt.ts")
    transcript = _read("web", "src", "utils", "transcriptViewPrefs.ts")

    assert "composerModeVariant" in room
    assert 'composerModeVariant === "discuss"' in room or "modeDiscuss" in room
    assert "sendReceiptLabel" in room
    assert "discuss_saved" in receipt
    assert "TranscriptViewOptions" in room or "showHumanSynthesis" in room
    assert "showPeerChannel" in room or "PEER_CHANNEL_KEY" in transcript
    assert "task-row--claimable" in taskbar
    assert "claimableIds" in taskbar


def test_scenario_b_plan_synthesis_contract():
    """B: plan after send → plan chip + Workbench/Plan surface."""
    room = _read("web", "src", "components", "RoomChat.tsx")
    work = _read("web", "src", "components", "WorkToolPanel.tsx")
    plan = _read("web", "src", "components", "PlanExecutePanel.tsx")

    assert "planAfterSend" in room
    assert "modePlan" in room or "plan_updated" in _read("web", "src", "utils", "sendReceipt.ts")
    assert "openPlanTab" in room
    assert 'rightPanelMode === "plan"' in room
    assert "WorkbenchPanel" in room
    assert "PlanExecutePanel" in work
    assert "MissionOverviewSection" not in work
    assert "plan-card" in plan
    assert "지금 실행" in plan or "nowItems" in plan


def test_scenario_b2_plan_workflow_ui_contract():
    """B2: plan workflow phase banner + reject target_phase + receipts/SSE."""
    room = _read("web", "src", "components", "RoomChat.tsx")
    banner = _read("web", "src", "components", "PlanWorkflowBanner.tsx")
    approval = _read("web", "src", "components", "PlanApprovalPanel.tsx")
    receipt = _read("web", "src", "utils", "sendReceipt.ts")
    plan_view = _read("web", "src", "utils", "planWorkflowView.ts")

    assert "PlanWorkflowBanner" in room
    assert "showPlanWorkflowBanner" in room
    assert "showPlanWorkflowComposerHint" in room
    assert "plan_workflow_phase" in room
    assert "plan_workflow_pending" in room
    assert "sendReceiptRaw" in room
    assert "plan-workflow-banner" in banner
    assert "HUMAN_PENDING" in banner
    assert "APPROVED" in banner
    assert "CLARIFY" in banner
    assert "PEER_REVIEW" in banner
    assert "plan-reject-target" in approval
    assert "target_phase" in approval
    assert "PLAN_REJECT_TARGETS" in approval
    assert "plan_pending_approval" in receipt
    assert "isPlanWorkflowSendReceipt" in receipt
    assert "planWorkflowPhaseTranscriptLine" in plan_view


def test_scenario_b_diff_tool_contract():
    """B2: workbench diff mode renders execution diffs."""
    room = _read("web", "src", "components", "RoomChat.tsx")
    diff = _read("web", "src", "components", "DiffToolPanel.tsx")

    assert 'rightPanelMode === "diff"' in room
    assert "DiffToolPanel" in room
    assert "PlanDiffStat" in diff
    assert "SideBySideDiff" in diff
    assert "출력할 diff 없음" in diff


def test_scenario_c_execute_task_contract():
    """C: dry-run, cross-link footer, complete gate 409."""
    taskbar = _read("web", "src", "components", "RoomTaskBar.tsx")
    plan = _read("web", "src", "components", "PlanExecutePanel.tsx")
    copy = _read("web", "src", "utils", "taskBarCopy.ts")

    assert "buildTaskCrossLinks" in copy
    assert "taskbar__cross-links" in taskbar
    assert "taskCompleteGate" in taskbar
    assert "completeErrors" in taskbar
    assert "handleDryRun" in plan or "dry-run" in plan.lower()


def test_scenario_d_lead_consensus_contract():
    """D: turn leads, consensus blocker, consensus_done receipt."""
    taskbar = _read("web", "src", "components", "RoomTaskBar.tsx")
    room = _read("web", "src", "components", "RoomChat.tsx")
    receipt = _read("web", "src", "utils", "sendReceipt.ts")

    assert "turnLeadEntries" in taskbar
    assert "taskbar__turn-lead-chip" in taskbar
    assert "showConsensusBlocker" in taskbar
    assert "consensus_done" in receipt
    assert "composer--consensus-mode" in room


def test_scenario_e_clarifier_contract():
    """E: clarifier banner when AGENT_LAB_CLARIFIER=1."""
    room = _read("web", "src", "components", "RoomChat.tsx")

    assert "clarifierQuestions" in room
    assert "clarifier" in room.lower()


def test_m6_taskbar_no_legacy_room_task_bar_classes():
    taskbar = _read("web", "src", "components", "RoomTaskBar.tsx")
    assert "room-task-bar__" not in taskbar
    assert 'className="taskbar' in taskbar


def test_claude_bridge_wired_in_room():
    room_py = _read("src", "agent_lab", "room.py")
    assert 'aid in ("cursor", "codex", "claude")' in room_py


def test_new_session_mission_template_picker_contract():
    """NewSessionDialog ↔ /api/templates + apply on session bind."""
    ns = _read("web", "src", "components", "NewSessionDialog.tsx")
    app = _read("web", "src", "App.tsx")
    room = _read("web", "src", "components", "RoomChat.tsx")
    assert "fetchMissionTemplates" in ns
    assert "missionTemplateId" in ns
    assert "bootstrapMissionTemplateId" in app
    assert "applySessionTemplate" in room
    assert "bootstrapMissionTemplateId" in room
