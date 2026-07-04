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
    execute_send = _read("web", "src", "hooks", "useRoomExecuteSend.ts")
    transcript_panel = _read("web", "src", "components", "RoomTranscriptPanel.tsx")
    _read("web", "src", "components", "ChatComposer.tsx")
    taskbar = _read("web", "src", "components", "RoomTaskBar.tsx")
    receipt = _read("web", "src", "utils", "sendReceipt.ts")
    transcript = _read("web", "src", "utils", "transcriptViewPrefs.ts")

    assert "composerModeVariant" in room
    assert 'composerModeVariant === "discuss"' in room or "modeDiscuss" in room
    assert "sendReceiptLabel" in execute_send
    assert "discuss_saved" in receipt
    assert "TranscriptViewOptions" in transcript_panel or "showHumanSynthesis" in transcript_panel
    assert "showPeerChannel" in transcript_panel or "PEER_CHANNEL_KEY" in transcript
    assert "task-row--claimable" in taskbar
    assert "claimableIds" in taskbar


def test_turn_policy_workspace_binding_kept():
    """F2: Room permissions SSOT keeps session workspace binding without discuss overlay."""
    messages = _read("src", "agent_lab", "room", "messages.py")
    assert "effective_agent_permissions" in messages
    assert "apply_discuss_workspace" in messages
    assert "_effective_room_permissions" in messages
    turn_policy = _read("src", "agent_lab", "room", "turn_policy.py")
    assert "turn_policy_enabled" in turn_policy
    assert "apply_turn_effects" in turn_policy


def test_scenario_b_plan_synthesis_contract():
    """B: plan after send → composer event stack + execute surface."""
    room = _read("web", "src", "components", "RoomChat.tsx")
    inspector = _read("web", "src", "components", "RoomChatInspector.tsx")
    stack = _read("web", "src", "components", "ComposerEventStack.tsx")
    work = _read("web", "src", "components", "WorkToolPanel.tsx")
    plan = _read("web", "src", "components", "PlanExecutePanel.tsx")

    assert "composerModeVariant" in room
    assert "plan_updated" in _read("web", "src", "utils", "sendReceipt.ts")
    assert "ComposerEventStack" in room
    assert "focusComposerStack" in room
    assert "WorkbenchPanel" in inspector
    assert "PlanExecutePanel" in work
    assert "WorkPlanApprovalSection" in stack
    assert "plan-card" in plan
    assert "지금 실행" in plan or "nowItems" in plan


def test_scenario_b2_plan_workflow_ui_contract():
    room = _read("web", "src", "components", "RoomChat.tsx")
    sse = _read("web", "src", "hooks", "useRoomSseHandler.ts")
    approval = _read("web", "src", "components", "PlanApprovalPanel.tsx")
    receipt = _read("web", "src", "utils", "sendReceipt.ts")
    plan_view = _read("web", "src", "utils", "planWorkflowView.ts")

    main_pane = _read("web", "src", "components", "RoomChatMainPane.tsx")

    assert "RoomChatMainPane" in room
    assert "ComposerDecisionSurface" in main_pane
    assert "showPlanWorkflowBanner" in room
    assert "showPlanWorkflowComposerHint" in room
    assert "plan_workflow_phase" in sse
    assert "plan_workflow_pending" in sse
    assert "sendReceiptRaw" in room
    assert "HUMAN_PENDING" in room or "showPlanApproval" in room
    assert "renderPlanMarkdown" in approval
    assert 'onApprove("execute")' in approval
    assert 'onApprove("approve_only")' in approval
    assert "plan-reject-target" not in approval
    assert "plan-approval-promise" not in approval
    assert "target_phase" in approval
    assert 'target_phase: "REFINE"' in approval
    assert "plan_pending_approval" in receipt
    assert "isPlanWorkflowSendReceipt" in receipt
    assert "planWorkflowPhaseTranscriptLine" in plan_view


def test_scenario_b_diff_tool_contract():
    """B2: workbench diff mode renders execution diffs."""
    room = _read("web", "src", "components", "RoomChat.tsx")
    inspector = _read("web", "src", "components", "RoomChatInspector.tsx")
    diff = _read("web", "src", "components", "DiffToolPanel.tsx")

    assert 'rightPanelMode === "diff"' in inspector
    assert "DiffToolPanel" in inspector
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
    room_py = _read("src", "agent_lab", "room", "agent_invoke.py")
    # Phase 2: bridge/activity wired for every agent (incl. kimi/local substitutes),
    # not gated to the static cloud trio.
    assert "on_bridge_event=_bridge_event" in room_py
    assert "on_activity=_activity" in room_py


def test_new_session_mission_template_apply_contract():
    """NewSessionDialog now loads consolidated session-setup options; the mission-template
    apply path survives in RoomChat SSE handler (bootstrap id -> applySessionTemplate on session bind).
    (The standalone template picker was consolidated out of NewSessionDialog/App.)"""
    ns = _read("web", "src", "components", "NewSessionDialog.tsx")
    room = _read("web", "src", "components", "RoomChat.tsx")
    sse = _read("web", "src", "hooks", "useRoomSseHandler.ts")
    assert "fetchSessionSetupOptions" in ns
    assert "applySessionTemplate" in sse
    assert "bootstrapMissionTemplateId" in room or "pendingMissionTemplateRef" in sse


def test_taskbar_human_inbox_integration_contract():
    """Human gate resolve: composer event stack. RoomTaskBar remains unmounted."""
    taskbar = _read("web", "src", "components", "RoomTaskBar.tsx")
    stack = _read("web", "src", "components", "ComposerEventStack.tsx")
    room = _read("web", "src", "components", "RoomChat.tsx")
    assert "taskbar--dock" in taskbar
    assert "HumanInboxPanel" in stack
    assert "taskbar-dock" not in room
    assert "RoomTaskBar" not in room
    assert "InspectorTasksSummary" not in room
    assert "ComposerEventStack" in room
    assert "openHumanInbox" in room


def test_inbox_segments_contract():
    """Activity inline in transcript; Human Inbox in composer stack."""
    room = _read("web", "src", "components", "RoomChat.tsx")
    transcript = _read("web", "src", "components", "RoomTranscriptPanel.tsx")
    sse = _read("web", "src", "hooks", "useRoomSseHandler.ts")
    stack = _read("web", "src", "components", "ComposerEventStack.tsx")
    assert "TranscriptActivityDivider" in transcript
    assert "appendTranscriptActivity" in _read(
        "web", "src", "utils", "pushNotification.ts"
    )
    assert 'inboxSegment === "inbox"' not in room
    assert 't === "inbox_pause"' in sse
    assert 'presentation="composer"' in stack
    inbox = _read("web", "src", "components", "HumanInboxPanel.tsx")
    assert "inbox-row--fork" in inbox
    assert "inbox-row__kind-badge" in inbox


def test_composer_question_inbox_is_separate_from_generic_pending_hint():
    room = _read("web", "src", "components", "RoomChat.tsx")
    stack = _read("web", "src", "components", "ComposerEventStack.tsx")
    inbox = _read("web", "src", "components", "HumanInboxPanel.tsx")
    assert "inboxPendingCount" in room
    assert 'presentation="composer"' in stack
    assert "ComposerEventStack" in room
    assert "visiblePending.map" in inbox
    assert "visiblePending[0]?.kind" in inbox


def test_room_preset_picker_replaces_turn_strategy_ui():
    composer = _read("web", "src", "components", "ChatComposer.tsx")
    presets = _read("web", "src", "utils", "roomPresets.ts")
    room = _read("web", "src", "components", "RoomChat.tsx")
    composer_prefs = _read("web", "src", "hooks", "useRoomComposerPrefs.ts")
    assert "ComposerTurnPicker" not in composer
    assert "resolveRoomPresets" in presets
    assert "presetDisplayLabel" in presets
    assert "resolveRoomPresets" in composer_prefs
    assert "onRoomPresetSelect" in room and "selectRoomPreset" in room
    assert "ACTIVE_ROOM_PRESET_IDS" not in room


def test_m6_work_exec_classes_only_in_plan_execute_panel():
    panel = _read("web", "src", "components", "PlanExecutePanel.tsx")
    assert "plan-execute-" not in panel
    assert "work-exec-" in panel
    assert "plan-card__btn" in panel


def test_human_decision_banner_contract():
    """D: unified Human decision surface from runtime gates."""
    surface = _read("web", "src", "components", "ComposerDecisionSurface.tsx")
    banner = _read("web", "src", "components", "HumanDecisionBanner.tsx")
    view = _read("web", "src", "utils", "humanDecisionView.ts")
    hook = _read("web", "src", "hooks", "useHumanDecisionRuntime.ts")
    css = _read("web", "src", "styles", "prototype-panels.css")

    assert "ComposerNoticeCard" in surface
    assert "human_gate" in surface
    assert "workspace-discuss-pause-banner" not in surface
    assert "shouldShowHumanDecisionBanner" in view
    assert "useHumanDecisionRuntime" in hook
    assert "humanDecisionTitle" in banner
    assert "composer-notice-card" in css


def test_plan_workflow_banner_hides_inbox_when_human_decision_visible():
    """Plan workflow inbox CTA defers when human gate is active."""
    banner = _read("web", "src", "components", "PlanWorkflowBanner.tsx")
    surface = _read("web", "src", "components", "ComposerDecisionSurface.tsx")
    priority = _read("web", "src", "utils", "composerDecisionPriority.ts")
    assert "hideInboxButton" in banner
    assert "showHumanGate" in surface
    assert '"human_gate"' in priority
    assert "pickComposerDecisionTier" in surface


def test_remaining_gaps_slack_inbox_ref_recovery_contract():
    """Slack settings, inbox ref jump, discuss recovery banner."""
    room = _read("web", "src", "components", "RoomChat.tsx")
    gateway = _read("web", "src", "components", "GatewaySettingsPanel.tsx")
    recovery = _read("web", "src", "components", "RecoveryStrip.tsx")
    recovery_handlers = _read("web", "src", "hooks", "useRoomRecoveryHandlers.ts")
    ref_nav = _read("web", "src", "utils", "inboxRefNavigation.ts")
    client = _read("web", "src", "api", "client.ts")
    css = _read("web", "src", "styles", "prototype-panels.css")

    assert "missionOsSlackSigningSecret" in gateway or "slackSigningSecret" in gateway
    assert "activateInboxRef" in room
    assert "handleInboxRefClick" in room
    event_stack = _read("web", "src", "hooks", "useRoomComposerEventStack.tsx")
    assert "onInboxRefClick: handleInboxRefClick" in event_stack
    main_pane = _read("web", "src", "components", "RoomChatMainPane.tsx")

    assert "RoomChatMainPane" in room
    assert "ComposerDecisionSurface" in main_pane
    assert "RecoveryStrip" in recovery
    assert "postMissionDiscussRecovery" in recovery_handlers
    assert "DiscussRecoveryBanner" in _read(
        "web", "src", "components", "DiscussRecoveryBanner.tsx"
    )
    assert "run_discuss_recovery" in recovery
    assert "recovery-strip" in recovery
    assert "parseInboxRef" in ref_nav
    assert "postMissionDiscussRecovery" in client
    assert "inbox-row__ref-link" in css
    assert "discuss-recovery-banner" in css
