import { useMemo, type ComponentProps, type Ref } from "react";
import type {
  PlanWorkflowRecord,
  RoomObjection,
  RuntimeSnapshot,
  SlashCommandRecord,
} from "../api/client";
import type { useLocale } from "../i18n/useLocale";
import { buildDecisionBlockedHeadline } from "../utils/decisionBlockedHeadline";
import type { RecoveryActionId, RecoveryItem } from "../utils/recoveryItems";
import type {
  RecoveryLifecycleView,
  RecoveryResolutionEvent,
  RecoveryRetryActionId,
} from "../utils/recoveryLifecycle";
import type { AgentPermissions } from "../utils/agentPermissions";
import { AgentPermissionAlert } from "./AgentPermissionAlert";
import { ComposerDecisionSurface } from "./ComposerDecisionSurface";
import { MacAlert } from "./MacAlert";
import { RoomChatComposerShell } from "./RoomChatComposerShell";
import { RoomTranscriptPanel } from "./RoomTranscriptPanel";

type TranscriptProps = ComponentProps<typeof RoomTranscriptPanel>;
type ComposerShellProps = ComponentProps<typeof RoomChatComposerShell>;

type Props = {
  isNew: boolean;
  sessionId: string | null;
  avoidWorkbenchNotice: boolean;
  locale: ReturnType<typeof useLocale>["locale"];
  inboxPendingCount: number;
  inboxReloadKey: number;
  discussPaused: boolean;
  decisionRuntime: RuntimeSnapshot | null;
  showPlanApproval: boolean;
  verifiedLoopPendingApproval: boolean;
  firstOpenBlock: RoomObjection | null;
  consensusBlocked: boolean;
  planWorkflow: PlanWorkflowRecord | undefined;
  planWorkflowPlanIntent: string | null;
  showPlanWorkflowBanner: boolean;
  showPlanWorkflowComposerHint: boolean;
  recoveryVisible: boolean;
  recoveryLifecycleView: RecoveryLifecycleView;
  recoveryBusyActionId: RecoveryActionId | null;
  composerNoticeDismissed: string | null;
  onOpenInbox: () => void;
  onOpenWork: () => void;
  onRecoveryAction: (
    actionId: RecoveryActionId,
    item: RecoveryItem,
  ) => void | Promise<void>;
  onRecoveryRetryAction: (
    actionId: RecoveryRetryActionId,
    event: RecoveryResolutionEvent,
  ) => void;
  onRecoveryDismiss: () => void;
  onDismissNotice: (key: string) => void;
  scrollRef: Ref<HTMLDivElement>;
  transcript: TranscriptProps;
  composerShell: ComposerShellProps;
  externalCommandConfirm: {
    command: SlashCommandRecord;
    args: string;
  } | null;
  onExternalCommandDismiss: () => void;
  onExternalCommandExecute: (command: SlashCommandRecord, args: string) => void;
  permOpen: boolean;
  showPermAlert: boolean;
  permissionSelectedAgents: string[];
  onPermissionCancel: () => void;
  onPermissionConfirm: (permissions: AgentPermissions) => void;
};

/** Center workspace column — decision/recovery notice, transcript, composer (F9). */
export function RoomChatMainPane({
  isNew,
  sessionId,
  avoidWorkbenchNotice,
  locale,
  inboxPendingCount,
  inboxReloadKey,
  discussPaused,
  decisionRuntime,
  showPlanApproval,
  verifiedLoopPendingApproval,
  firstOpenBlock,
  consensusBlocked,
  planWorkflow,
  planWorkflowPlanIntent,
  showPlanWorkflowBanner,
  showPlanWorkflowComposerHint,
  recoveryVisible,
  recoveryLifecycleView,
  recoveryBusyActionId,
  composerNoticeDismissed,
  onOpenInbox,
  onOpenWork,
  onRecoveryAction,
  onRecoveryRetryAction,
  onRecoveryDismiss,
  onDismissNotice,
  scrollRef,
  transcript,
  composerShell,
  externalCommandConfirm,
  onExternalCommandDismiss,
  onExternalCommandExecute,
  permOpen,
  showPermAlert,
  permissionSelectedAgents,
  onPermissionCancel,
  onPermissionConfirm,
}: Props) {
  const decisionBlockedHeadline = useMemo(
    () =>
      buildDecisionBlockedHeadline({
        locale,
        inboxPendingCount,
        discussPaused,
        runtime: decisionRuntime,
        showPlanApproval,
        verifiedLoopPendingApproval,
        firstOpenBlock,
        consensusBlocked,
        planWorkflow,
      }),
    [
      locale,
      inboxPendingCount,
      discussPaused,
      decisionRuntime,
      showPlanApproval,
      verifiedLoopPendingApproval,
      firstOpenBlock,
      consensusBlocked,
      planWorkflow,
    ],
  );

  return (
    <div className="workspace-body">
      {!isNew && sessionId ? (
        <div
          className={`composer-notice-floating${
            avoidWorkbenchNotice ? " composer-notice-floating--left" : ""
          }`}
        >
          <ComposerDecisionSurface
            sessionId={sessionId}
            inboxPendingCount={inboxPendingCount}
            inboxReloadKey={inboxReloadKey}
            discussPaused={discussPaused}
            blockedHeadline={decisionBlockedHeadline}
            recoveryVisible={recoveryVisible}
            recoveryItems={recoveryLifecycleView.activeItems}
            recoveryResolvedEvents={recoveryLifecycleView.resolvedEvents}
            recoveryCanRetrySend={
              recoveryLifecycleView.retryState.canFocusComposer
            }
            recoveryBusyActionId={recoveryBusyActionId}
            showPlanApproval={showPlanApproval}
            showPlanWorkflowBanner={showPlanWorkflowBanner}
            showPlanWorkflowComposerHint={showPlanWorkflowComposerHint}
            planWorkflow={planWorkflow}
            planWorkflowPlanIntent={planWorkflowPlanIntent}
            dismissedKey={composerNoticeDismissed}
            onOpenInbox={onOpenInbox}
            onOpenWork={onOpenWork}
            onRecoveryAction={(actionId, item) =>
              void onRecoveryAction(actionId, item)
            }
            onRecoveryRetryAction={onRecoveryRetryAction}
            onRecoveryDismiss={onRecoveryDismiss}
            onDismissNotice={onDismissNotice}
          />
        </div>
      ) : null}

      <div className="workspace-scroll scroll-y" ref={scrollRef}>
        <RoomTranscriptPanel {...transcript} />
      </div>

      <RoomChatComposerShell {...composerShell} />

      <MacAlert
        open={externalCommandConfirm !== null}
        title="외부 명령 실행"
        message={
          externalCommandConfirm
            ? `${externalCommandConfirm.command.label} (${externalCommandConfirm.command.slash}) — 로컬 subprocess를 실행합니다. Settings에서 allowlist에 포함된 명령만 실행됩니다.`
            : undefined
        }
        buttons={[
          {
            label: "취소",
            variant: "cancel",
            onClick: onExternalCommandDismiss,
          },
          {
            label: "실행",
            variant: "primary",
            onClick: () => {
              const pending = externalCommandConfirm;
              onExternalCommandDismiss();
              if (pending) {
                onExternalCommandExecute(pending.command, pending.args);
              }
            },
          },
        ]}
        onClose={onExternalCommandDismiss}
      />

      <AgentPermissionAlert
        open={permOpen || showPermAlert}
        selectedAgents={permissionSelectedAgents}
        onCancel={onPermissionCancel}
        onConfirm={onPermissionConfirm}
      />
    </div>
  );
}
