import type { PlanWorkflowRecord } from "../api/client";
import { useLocale } from "../i18n/useLocale";

type Props = {
  workflow: PlanWorkflowRecord;
  inboxPendingCount?: number;
  running?: boolean;
  onOpenInbox?: () => void;
};

function phaseLabel(
  phase: string,
  msg: ReturnType<typeof useLocale>["msg"],
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
    default:
      return null;
  }
}

export function PlanWorkflowBanner({
  workflow,
  inboxPendingCount = 0,
  running = false,
  onOpenInbox,
}: Props) {
  const { msg } = useLocale();
  const phase = (workflow.phase ?? "").toUpperCase();
  const copy = phaseLabel(phase, msg);
  if (!copy) return null;

  const roundBits: string[] = [];
  if (typeof workflow.clarify_round === "number" && workflow.clarify_round > 0) {
    roundBits.push(`CLARIFY R${workflow.clarify_round}`);
  }
  if (typeof workflow.peer_review_round === "number" && workflow.peer_review_round > 0) {
    roundBits.push(`PEER R${workflow.peer_review_round}`);
  }

  return (
    <div
      className="clarifier-banner plan-workflow-banner"
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
      {roundBits.length > 0 ? (
        <p className="plan-workflow-banner__meta">{roundBits.join(" · ")}</p>
      ) : null}
      {(phase === "CLARIFY" || phase === "INTAKE") && inboxPendingCount > 0 ? (
        <button
          type="button"
          className="btn btn--sm plan-workflow-banner__inbox"
          onClick={onOpenInbox}
        >
          {msg.planWorkflowOpenInbox(inboxPendingCount)}
        </button>
      ) : null}
    </div>
  );
}
