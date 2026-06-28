import type { PlanWorkflowRecord } from "../api/client";
import type { RecoveryActionId, RecoveryItem } from "../utils/recoveryItems";
import type {
  RecoveryResolutionEvent,
  RecoveryRetryActionId,
} from "../utils/recoveryLifecycle";
import type { DecisionBlockedHeadline } from "../utils/decisionBlockedHeadline";
import { pickComposerDecisionTier } from "../utils/composerDecisionPriority";
import { useHumanDecisionRuntime } from "../hooks/useHumanDecisionRuntime";
import { useLocale } from "../i18n/useLocale";
import { planWorkflowNoticeLabel } from "../utils/planWorkflowView";
import { ComposerNoticeCard } from "./ComposerNoticeCard";

type Props = {
  readonly sessionId: string | null;
  readonly inboxPendingCount: number;
  readonly inboxReloadKey: number;
  readonly discussPaused: boolean;
  readonly blockedHeadline: DecisionBlockedHeadline;
  readonly recoveryVisible: boolean;
  readonly recoveryItems: readonly RecoveryItem[];
  readonly recoveryResolvedEvents: readonly RecoveryResolutionEvent[];
  readonly recoveryCanRetrySend: boolean;
  readonly recoveryBusyActionId: RecoveryActionId | null;
  readonly showPlanApproval: boolean;
  readonly showPlanWorkflowBanner: boolean;
  readonly showPlanWorkflowComposerHint: boolean;
  readonly planWorkflow: PlanWorkflowRecord | undefined;
  readonly planWorkflowPlanIntent: string | null;
  readonly onOpenInbox: () => void;
  readonly onOpenWork: () => void;
  readonly onRecoveryAction: (
    actionId: RecoveryActionId,
    item: RecoveryItem,
  ) => void;
  readonly onRecoveryRetryAction: (
    actionId: RecoveryRetryActionId,
    event: RecoveryResolutionEvent,
  ) => void;
  readonly onRecoveryDismiss: () => void;
};

export function ComposerDecisionSurface({
  sessionId,
  inboxPendingCount,
  inboxReloadKey,
  discussPaused,
  blockedHeadline,
  recoveryVisible,
  recoveryItems,
  recoveryBusyActionId,
  showPlanApproval,
  showPlanWorkflowBanner,
  showPlanWorkflowComposerHint,
  planWorkflow,
  planWorkflowPlanIntent,
  onOpenInbox,
  onOpenWork,
  onRecoveryAction,
  onRecoveryDismiss,
}: Props) {
  const { locale, msg } = useLocale();
  const ko = locale === "ko";
  const { visible: showHumanGate, runtime } = useHumanDecisionRuntime(
    sessionId,
    inboxReloadKey,
    discussPaused,
  );

  const tier = pickComposerDecisionTier({
    inboxPendingCount,
    recoveryVisible,
    showPlanApproval,
    showHumanGate,
    showPlanWorkflowBanner,
    showPlanWorkflowComposerHint,
    planWorkflowPhase: planWorkflow?.phase,
    planWorkflowNotice: planWorkflow?.notice,
    clarifierInterview: runtime?.clarifier_interview ?? null,
  });

  if (!tier) return null;

  if (tier === "recovery" && recoveryItems[0]) {
    const item = recoveryItems[0];
    const primaryBusy = recoveryBusyActionId === item.primaryAction.id;
    const secondary = item.secondaryAction;
    return (
      <ComposerNoticeCard
        variant="alert"
        title={item.title}
        description={item.reason}
        primaryLabel={primaryBusy ? msg.running : item.primaryAction.label}
        onPrimary={() => onRecoveryAction(item.primaryAction.id, item)}
        secondaryLabel={secondary?.label}
        onSecondary={
          secondary ? () => onRecoveryAction(secondary.id, item) : undefined
        }
        onDismiss={onRecoveryDismiss}
        dismissLabel={ko ? "닫기" : "Dismiss"}
        busy={Boolean(recoveryBusyActionId)}
      />
    );
  }

  if (tier === "plan_approval") {
    return (
      <ComposerNoticeCard
        title={blockedHeadline.headline}
        description={blockedHeadline.detail}
        primaryLabel={msg.planWorkflowPendingOpenTasks}
        onPrimary={onOpenWork}
      />
    );
  }

  if (tier === "human_gate") {
    return (
      <ComposerNoticeCard
        variant="alert"
        title={blockedHeadline.headline}
        description={blockedHeadline.detail}
        primaryLabel={msg.humanDecisionOpenInbox}
        onPrimary={onOpenInbox}
      />
    );
  }

  if (tier === "plan_workflow" && planWorkflow) {
    const phase = (planWorkflow.phase ?? "").toUpperCase();
    const notice = planWorkflowNoticeLabel(planWorkflow.notice, msg);
    const detail =
      notice ??
      (phase === "APPROVED"
        ? planWorkflowPlanIntent === "plan_only"
          ? msg.planWorkflowApprovedTeamDetail
          : msg.planWorkflowApprovedDetail
        : blockedHeadline.detail);
    const clarifyPhase = phase === "CLARIFY" || phase === "INTAKE";

    return (
      <ComposerNoticeCard
        title={blockedHeadline.headline}
        description={detail}
        primaryLabel={
          phase === "HUMAN_PENDING"
            ? msg.planWorkflowPendingOpenTasks
            : clarifyPhase
              ? msg.humanDecisionOpenInbox
              : ko
                ? "Work 열기"
                : "Open Work"
        }
        onPrimary={
          phase === "HUMAN_PENDING"
            ? onOpenWork
            : clarifyPhase
              ? onOpenInbox
              : onOpenWork
        }
      />
    );
  }

  return null;
}
