import { AutonomyDial } from "./AutonomyDial";
import { CommandPalette } from "./CommandPalette";
import { RoomChatInspector } from "./RoomChatInspector";
import { RoomChatMainPane } from "./RoomChatMainPane";
import { WorkspaceChrome } from "./WorkspaceChrome";
import { type RoomChatProps, useRoomChat } from "../hooks/useRoomChat";

export type { RoomChatProps };

export function RoomChat(props: RoomChatProps) {
  const chat = useRoomChat(props);

  return (
    <>
      <CommandPalette actions={chat.paletteActions} />

      <WorkspaceChrome
        title={chat.title}
        meta={chat.titleMeta}
        headerExtra={
          chat.sessionId ? (
            <AutonomyDial
              view={chat.autonomyView}
              loading={chat.autonomyLoading}
              changing={chat.autonomyChanging}
              disabled={chat.running || chat.runBusy}
              onLevelChange={chat.setAutonomyLevel}
            />
          ) : null
        }
        sidebarOpen={chat.sidebarOpen}
        rightPanelOpen={chat.inspectorOpen}
        rightPanelMode={chat.rightPanelMode}
        locale={chat.locale}
        onToggleSidebar={chat.onToggleSidebar}
        onToggleRightPanel={chat.toggleInspector}
        onSelectRightPanelMode={chat.handleSelectRightPanelMode}
        onOpenSettings={chat.onOpenSettings}
        onWorkbenchMenuOpenChange={chat.setWorkbenchMenuOpen}
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
              turnHint: chat.composerEmergenceHint ?? chat.composerPresetHint,
              costHint: chat.composerCostHint,
              locale: chat.locale,
              roomPresets: chat.visiblePresets,
              roomPreset: chat.roomPreset,
              onRoomPresetSelect: chat.selectRoomPreset,
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
                  chat.composeMode,
                  chat.pendingSend.turnProfile,
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
