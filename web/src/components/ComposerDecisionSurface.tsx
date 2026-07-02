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
  readonly dismissedKey?: string | null;
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
  readonly onDismissNotice?: (key: string) => void;
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
  dismissedKey = null,
  onOpenInbox,
  onRecoveryAction,
  onRecoveryDismiss,
  onDismissNotice,
}: Props) {
  const { locale, msg: _msg } = useLocale();
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
  if (dismissedKey === tier) return null;

  if (tier === "recovery" && recoveryItems[0]) {
    const item = recoveryItems[0];
    const primaryBusy = recoveryBusyActionId === item.primaryAction.id;
    const secondary = item.secondaryAction;
    return (
      <ComposerNoticeCard
        variant="alert"
        title={item.title}
        description={
          item.details && item.details.length > (item.reason?.length ?? 0)
            ? item.details
            : item.reason
        }
        primaryLabel={
          primaryBusy
            ? ko
              ? "처리 중…"
              : "Working…"
            : item.primaryAction.label
        }
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

  if (tier === "human_gate") {
    return (
      <ComposerNoticeCard
        variant="alert"
        title={blockedHeadline.headline}
        description={blockedHeadline.detail}
        primaryLabel={ko ? "Composer에서 확인" : "View in composer"}
        onPrimary={onOpenInbox}
        onDismiss={() => onDismissNotice?.("human_gate")}
        dismissLabel={ko ? "닫기" : "Dismiss"}
      />
    );
  }

  return null;
}
