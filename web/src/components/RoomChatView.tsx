import { AutonomyDial } from "./AutonomyDial";
import { CommandPalette } from "./CommandPalette";
import { NeedsInputBadge } from "./NeedsInputBadge";
import { RoomChatInspector } from "./RoomChatInspector";
import { RoomChatMainPane } from "./RoomChatMainPane";
import { SessionStatusLine } from "./SessionStatusLine";
import { WorkspaceChrome } from "./WorkspaceChrome";
import type { useRoomChat } from "../hooks/useRoomChat";
import { useEffect, useMemo } from "react";
import { buildNeedsInputStatus } from "../utils/needsInputStatus";
import { notifyNeedsInputIfBackground } from "../utils/notifyNeedsInput";
import { buildSessionStatusChips } from "../utils/sessionStatusLine";

type RoomChatViewModel = ReturnType<typeof useRoomChat>;

type Props = {
  chat: RoomChatViewModel;
};

export function RoomChatView({ chat }: Props) {
  const needsInput = useMemo(
    () =>
      buildNeedsInputStatus({
        locale: chat.locale,
        inboxPendingCount: chat.inboxPendingCount,
        inboxPendingQuestions: chat.inboxPendingQuestions ?? 0,
        inboxPendingBuilds: chat.inboxPendingBuilds ?? 0,
        inboxPendingAutonomy: chat.inboxPendingAutonomy ?? 0,
        showPlanApproval: chat.showPlanApproval,
        verifiedLoopPendingApproval: chat.verifiedLoopPendingApproval,
        execPendingApproval: Boolean(
          chat.execPendingForBar?.status === "pending_approval",
        ),
        discussPaused: chat.discussPaused,
        runtime: chat.decisionRuntime,
        planWorkflow: chat.planWorkflow,
      }),
    [
      chat.locale,
      chat.inboxPendingCount,
      chat.inboxPendingQuestions,
      chat.inboxPendingBuilds,
      chat.inboxPendingAutonomy,
      chat.showPlanApproval,
      chat.verifiedLoopPendingApproval,
      chat.execPendingForBar,
      chat.discussPaused,
      chat.decisionRuntime,
      chat.planWorkflow,
    ],
  );

  const statusChips = useMemo(
    () =>
      buildSessionStatusChips({
        runtime: chat.decisionRuntime,
        locale: chat.locale,
      }),
    [chat.decisionRuntime, chat.locale],
  );

  useEffect(() => {
    if (!chat.sessionId || !needsInput.active) return;
    notifyNeedsInputIfBackground({
      sessionId: chat.sessionId,
      status: needsInput,
      locale: chat.locale,
    });
  }, [chat.sessionId, chat.locale, needsInput]);

  return (
    <>
      <CommandPalette actions={chat.paletteActions} />

      <WorkspaceChrome
        title={chat.title}
        meta={chat.titleMeta}
        headerExtra={
          chat.sessionId ? (
            <>
              <NeedsInputBadge
                status={needsInput}
                onOpen={() => {
                  if (needsInput.focus === "plan_approval") {
                    chat.openWorkApproval();
                  } else if (needsInput.focus === "execute_queue") {
                    chat.focusWorkStack?.("execute");
                  } else {
                    chat.openHumanInbox();
                  }
                }}
              />
              <SessionStatusLine chips={statusChips} />
              <AutonomyDial
                view={chat.autonomyView}
                loading={chat.autonomyLoading}
                changing={chat.autonomyChanging}
                disabled={chat.running || chat.runBusy}
                onLevelChange={chat.setAutonomyLevel}
              />
            </>
          ) : null
        }
        sidebarOpen={chat.sidebarOpen}
        rightPanelOpen={chat.inspectorOpen}
        rightPanelMode={chat.rightPanelMode}
        locale={chat.locale}
        onToggleSidebar={chat.onToggleSidebar}
        onSelectRightPanelMode={chat.handleSelectRightPanelMode}
        onOpenSettings={chat.onOpenSettings}
      />

      <div className="pane-row">
        <div className="pane-main workspace-main">
          <RoomChatMainPane
            isNew={chat.isNew}
            sessionId={chat.sessionId}
            avoidWorkbenchNotice={chat.avoidWorkbenchNotice}
            locale={chat.locale}
            inboxPendingCount={chat.inboxPendingCount}
            inboxReloadKey={chat.inboxReloadKey}
            discussPaused={chat.discussPaused}
            decisionRuntime={chat.decisionRuntime}
            showPlanApproval={chat.showPlanApproval}
            verifiedLoopPendingApproval={chat.verifiedLoopPendingApproval}
            firstOpenBlock={chat.firstOpenBlock}
            consensusBlocked={chat.consensusBlocked}
            planWorkflow={chat.planWorkflow}
            planWorkflowPlanIntent={chat.planWorkflowPlanIntent}
            showPlanWorkflowBanner={chat.showPlanWorkflowBanner}
            showPlanWorkflowComposerHint={chat.showPlanWorkflowComposerHint}
            recoveryVisible={chat.recoveryVisible}
            recoveryLifecycleView={chat.recoveryLifecycleView}
            recoveryBusyActionId={chat.recoveryBusyActionId}
            composerNoticeDismissed={chat.composerNoticeDismissed}
            onOpenInbox={() => {
              chat.setComposerNoticeDismissed("human_gate");
              chat.openHumanInbox();
            }}
            onOpenWork={() => {
              chat.setComposerNoticeDismissed("plan_workflow");
              chat.openWorkApproval();
            }}
            onRecoveryAction={chat.handleRecoveryAction}
            onRecoveryRetryAction={chat.handleRecoveryRetryAction}
            onRecoveryDismiss={() =>
              chat.setRecoveryDismissedSig(chat.recoverySignature)
            }
            onDismissNotice={chat.setComposerNoticeDismissed}
            scrollRef={chat.transcript.scrollRef}
            transcript={{
              sessionId: chat.sessionId,
              isNew: chat.isNew,
              loading: chat.loading ?? false,
              running: chat.running,
              showPeerChannel: chat.transcript.showPeerChannel,
              onPeerChannelChange: chat.transcript.onPeerChannelChange,
              visibleMessages: chat.transcript.visibleMessages,
              advisorRationales: chat.transcript.advisorRationales,
              openDraftMessageIds: chat.transcript.openDraftMessageIds,
              pendingReplyAgents: chat.transcript.pendingReplyAgents,
              runStartedAt: chat.runStartedAt,
              highlightChatLine: chat.transcript.highlightChatLine,
              locale: chat.locale,
              transcriptLoading: chat.localeMsg.transcriptLoading,
              transcriptEmpty: chat.localeMsg.transcriptEmpty,
              transcriptEmptyHint: chat.localeMsg.transcriptEmptyHint,
              showJumpButton: chat.transcript.showJumpButton,
              forceScrollButton: chat.tweaks.forceScrollButton,
              scrollToBottom: chat.transcript.scrollToBottom,
              transcriptActive: chat.transcript.transcriptActive,
              onActivityOpen: chat.handleNotificationOpen,
            }}
            composerShell={{
              show: chat.isNew || chat.transcript.transcriptActive,
              tweaksPreflightDemo: chat.tweaks.preflightDemo,
              recoveryItemsLength: chat.recoveryItemsLength,
              readiness: chat.readiness,
              healthAgents: chat.healthAgents,
              selected: chat.selected,
              clarifierQuestions: chat.clarifierQuestions,
              clarifierInterview: chat.clarifierInterview,
              planWorkflowActive: chat.planWorkflowActive,
              planWorkflowPhase: chat.planWorkflow?.phase,
              longRunning: chat.longRunning,
              running: chat.running,
              onStop: chat.handleStop,
              steerEligible: chat.steerEligible,
              onSteer: chat.handleSteer,
              steerBusy: chat.steerBusy,
              sessionId: chat.sessionId,
              eventStack: chat.composerEventStack,
              sendReceipt: chat.sendReceipt,
              sendReceiptRaw: chat.sendReceiptRaw,
              composerClassName: chat.composerClassName,
              text: chat.text,
              onTextChange: chat.setText,
              onSend: chat.handleSend,
              slashCommands: chat.slashCommands,
              onSlashExecute: (cmd) =>
                void chat.runSlashCommand(cmd, cmd.slash),
              composerInputLocked: chat.composerInputLocked,
              composerSendLocked: chat.composerSendLocked,
              composerPlaceholder: chat.composerPlaceholder,
              pendingFiles: chat.pendingFiles,
              onFilesAdd: chat.addFiles,
              onFileRemove: (id) =>
                chat.setPendingFiles((f) => f.filter((x) => x.id !== id)),
              composerObjectionNotice: chat.composerObjectionNotice,
              onFocusObjection: chat.focusObjection,
              turnHint:
                chat.composerRoutingHint ??
                chat.composerEmergenceHint ??
                chat.composerPresetHint,
              costHint: chat.composerCostHint,
              locale: chat.locale,
              agents: chat.agents,
              onOpenModelPicker: () => {
                const command = chat.slashCommands.find(
                  (candidate) => candidate.id === "model",
                );
                if (command) void chat.executeSlashCommand(command, "");
              },
              choicePopover: chat.choicePopover,
              authPopover: chat.authPopover,
              authPickerPopover: chat.authPickerPopover,
              modelPopover: chat.modelPopoverNode,
              commandHint: chat.commandHint,
            }}
            externalCommandConfirm={chat.externalCommandConfirm}
            onExternalCommandDismiss={() =>
              chat.setExternalCommandConfirm(null)
            }
            onExternalCommandExecute={(command, args) => {
              void chat.executeSlashCommand(command, args, true);
            }}
            permOpen={chat.permOpen}
            showPermAlert={chat.tweaks.showPermAlert}
            permissionSelectedAgents={
              chat.tweaks.showPermAlert && !chat.permOpen
                ? ["cursor", "claude"]
                : chat.selected
            }
            onPermissionCancel={() => {
              chat.tweaks.setShowPermAlert(false);
              chat.setPermOpen(false);
              if (chat.pendingSend) {
                chat.setText(chat.pendingSend.text);
                chat.setPendingFiles(chat.pendingSend.files);
                chat.setPendingSend(null);
              }
            }}
            onPermissionConfirm={(permissions) => {
              chat.tweaks.setShowPermAlert(false);
              chat.setPermOpen(false);
              if (chat.pendingSend) {
                void chat.executeSend(
                  chat.pendingSend.text,
                  chat.pendingSend.files,
                  permissions,
                );
                chat.setPendingSend(null);
                chat.setText("");
                chat.setPendingFiles([]);
              }
            }}
          />
        </div>
      </div>

      <RoomChatInspector
        isNew={chat.isNew}
        inspectorOpen={chat.inspectorOpen}
        rightPanelMode={chat.rightPanelMode}
        locale={chat.locale}
        workbenchPanelWidth={chat.workbenchPanelWidth}
        onWidthChange={chat.setActiveWorkbenchWidth}
        onWidthCommit={chat.commitWorkbenchWidth}
        onClose={chat.toggleInspector}
        session={chat.session}
        sessionId={chat.sessionId}
        healthAgents={chat.healthAgents}
        goalView={chat.goalView}
        planMeta={chat.planMeta}
        onFocusObjection={chat.focusObjection}
        planExecutions={chat.planExecutions}
        filesFocusPath={chat.filesFocusPath}
        filesFocusRevision={chat.filesFocusRevision}
      />
    </>
  );
}
