import type { PlanWorkflowRecord } from "../api/client";
import { useLocale } from "../i18n/useLocale";
import {
  planWorkflowGateReason,
  planWorkflowNoticeLabel,
} from "../utils/planWorkflowView";

type Props = {
  workflow: PlanWorkflowRecord;
  inboxPendingCount?: number;
  running?: boolean;
  variant?: "full" | "compact";
  /** When HumanDecisionBanner is visible, avoid duplicate Open Inbox CTA. */
  hideInboxButton?: boolean;
  onOpenInbox?: () => void;
  onOpenTasks?: () => void;
};

function phaseLabel(
  phase: string,
  msg: ReturnType<typeof useLocale>["msg"],
  variant: "full" | "compact",
): { title: string; detail: string; badge: string } | null {
  switch (phase) {
    case "INTAKE":
    case "CLARIFY":
      return {
        title: msg.planWorkflowClarifyTitle,
        detail: msg.planWorkflowClarifyDetail,
        badge: msg.planWorkflowPhaseClarify,
      };
    case "DRAFT":
      return {
        title: msg.planWorkflowDraftTitle,
        detail: msg.planWorkflowDraftDetail,
        badge: msg.planWorkflowPhaseDraft,
      };
    case "PEER_REVIEW":
      return {
        title: msg.planWorkflowPeerTitle,
        detail: msg.planWorkflowPeerDetail,
        badge: msg.planWorkflowPhasePeer,
      };
    case "REFINE":
      return {
        title: msg.planWorkflowRefineTitle,
        detail: msg.planWorkflowRefineDetail,
        badge: msg.planWorkflowPhaseRefine,
      };
    case "HUMAN_PENDING":
      return variant === "compact"
        ? {
            title: msg.planWorkflowPendingTitle,
            detail: msg.planWorkflowPendingDetail,
            badge: msg.planWorkflowPhasePending,
          }
        : null;
    case "APPROVED":
      return {
        title: msg.planWorkflowApprovedTitle,
        detail: msg.planWorkflowApprovedDetail,
        badge: msg.planWorkflowPhaseApproved,
      };
    default:
      return null;
  }
}

export function PlanWorkflowBanner({
  workflow,
  inboxPendingCount = 0,
  running = false,
  variant = "full",
  hideInboxButton = false,
  onOpenInbox,
  onOpenTasks,
}: Props) {
  const { msg } = useLocale();
  const phase = (workflow.phase ?? "").toUpperCase();
  const copy = phaseLabel(phase, msg, variant);
  if (!copy) return null;

  const roundBits: string[] = [];
  if (
    typeof workflow.clarify_round === "number" &&
    workflow.clarify_round > 0
  ) {
    roundBits.push(`CLARIFY R${workflow.clarify_round}`);
  }
  if (
    typeof workflow.peer_review_round === "number" &&
    workflow.peer_review_round > 0
  ) {
    roundBits.push(`PEER R${workflow.peer_review_round}`);
  }

  const noticeLabel = planWorkflowNoticeLabel(workflow.notice, msg);
  const gateReason = planWorkflowGateReason(workflow.last_plan_gate);

  return (
    <div
      className={[
        "clarifier-banner",
        "plan-workflow-banner",
        variant === "compact" ? "plan-workflow-banner--compact" : undefined,
        phase === "APPROVED" ? "plan-workflow-banner--approved" : undefined,
        phase === "HUMAN_PENDING" ? "plan-workflow-banner--pending" : undefined,
      ]
        .filter(Boolean)
        .join(" ")}
      role="region"
      aria-label={msg.planWorkflowBannerAria}
    >
      <div className="plan-workflow-banner__head">
        <strong className="clarifier-banner__title">{copy.title}</strong>
        <span className="plan-workflow-banner__badge">{copy.badge}</span>
        {running ? (
          <span className="plan-workflow-banner__badge plan-workflow-banner__badge--active">
            {msg.running}
          </span>
        ) : null}
      </div>
      <p className="clarifier-banner__hint">{copy.detail}</p>
      {noticeLabel ? (
        <p className="plan-workflow-banner__warn">{noticeLabel}</p>
      ) : null}
      {gateReason ? (
        <p className="plan-workflow-banner__warn">
          {msg.planWorkflowGateWarn(gateReason)}
        </p>
      ) : null}
      {roundBits.length > 0 ? (
        <p className="plan-workflow-banner__meta">{roundBits.join(" · ")}</p>
      ) : null}
      {(phase === "CLARIFY" || phase === "INTAKE") &&
      inboxPendingCount > 0 &&
      !hideInboxButton ? (
        <button
          type="button"
          className="btn btn--sm plan-workflow-banner__inbox"
          onClick={onOpenInbox}
        >
          {msg.planWorkflowOpenInbox(inboxPendingCount)}
        </button>
      ) : null}
      {phase === "HUMAN_PENDING" && variant === "compact" && onOpenTasks ? (
        <button
          type="button"
          className="btn btn--sm btn--primary plan-workflow-banner__tasks"
          onClick={onOpenTasks}
        >
          {msg.planWorkflowPendingOpenTasks}
        </button>
      ) : null}
    </div>
  );
}
