import type { useLocale } from "../i18n/useLocale";

export type PlanRejectTarget = "CLARIFY" | "DRAFT" | "REFINE";

export const PLAN_REJECT_TARGETS: PlanRejectTarget[] = [
  "CLARIFY",
  "DRAFT",
  "REFINE",
];

export function isPlanWorkflowPhaseBanner(phase: string | undefined): boolean {
  const p = (phase ?? "").toUpperCase();
  return (
    p === "INTAKE" ||
    p === "CLARIFY" ||
    p === "DRAFT" ||
    p === "PEER_REVIEW" ||
    p === "REFINE"
  );
}

export function isPlanWorkflowComposerHint(phase: string | undefined): boolean {
  const p = (phase ?? "").toUpperCase();
  return p === "HUMAN_PENDING" || p === "APPROVED";
}

type ClarifierInterviewLike = {
  readonly questions?: readonly {
    readonly prompt?: string;
    readonly answered?: boolean;
  }[];
};

export function pendingClarifierQuestionCount(
  interview: ClarifierInterviewLike | null | undefined,
): number {
  const questions = interview?.questions ?? [];
  return questions.filter((q) => q.prompt?.trim() && !q.answered).length;
}

/** CLARIFY/INTAKE only — inbox, open questions, or workflow notice. */
export function hasPlanWorkflowClarifySurface(input: {
  readonly phase?: string;
  readonly inboxPendingCount: number;
  readonly notice?: string;
  readonly clarifierInterview?: ClarifierInterviewLike | null;
}): boolean {
  const phase = (input.phase ?? "").toUpperCase();
  if (phase !== "CLARIFY" && phase !== "INTAKE") return false;
  if (input.inboxPendingCount > 0) return true;
  if (input.notice?.trim()) return true;
  return pendingClarifierQuestionCount(input.clarifierInterview) > 0;
}

export function shouldShowPlanWorkflowComposerNotice(input: {
  readonly showBanner: boolean;
  readonly showHint: boolean;
  readonly phase?: string;
  readonly inboxPendingCount: number;
  readonly notice?: string;
  readonly clarifierInterview?: ClarifierInterviewLike | null;
}): boolean {
  if (!input.showBanner && !input.showHint) return false;
  const phase = (input.phase ?? "").toUpperCase();
  if (phase === "CLARIFY" || phase === "INTAKE") {
    return hasPlanWorkflowClarifySurface({
      phase,
      inboxPendingCount: input.inboxPendingCount,
      notice: input.notice,
      clarifierInterview: input.clarifierInterview,
    });
  }
  return true;
}

export function planWorkflowNoticeLabel(
  notice: string | undefined,
  msg: ReturnType<typeof useLocale>["msg"],
): string | null {
  switch (notice) {
    case "clarify_cap_reached":
      return msg.planWorkflowNoticeClarifyCap;
    case "peer_review_cap_reached":
      return msg.planWorkflowNoticePeerCap;
    case "plan_gate_cap_reached":
      return msg.planWorkflowNoticeGateCap;
    default:
      return null;
  }
}

export function planWorkflowGateReason(gate: unknown): string | null {
  if (!gate || typeof gate !== "object") return null;
  const row = gate as Record<string, unknown>;
  const reason = row.reason ?? row.message ?? row.summary;
  return typeof reason === "string" && reason.trim() ? reason.trim() : null;
}

export function planWorkflowPhaseTranscriptLine(
  phase: string,
  msg: ReturnType<typeof useLocale>["msg"],
  notice?: string,
): string {
  const p = phase.toUpperCase();
  let line = "";
  switch (p) {
    case "INTAKE":
    case "CLARIFY":
      line = msg.planWorkflowTranscriptClarify;
      break;
    case "DRAFT":
      line = msg.planWorkflowTranscriptDraft;
      break;
    case "PEER_REVIEW":
      line = msg.planWorkflowTranscriptPeer;
      break;
    case "REFINE":
      line = msg.planWorkflowTranscriptRefine;
      break;
    case "HUMAN_PENDING":
      line = msg.planWorkflowTranscriptPending;
      break;
    case "APPROVED":
      line = msg.planWorkflowTranscriptApproved;
      break;
    default:
      line = msg.planWorkflowTranscriptGeneric(phase);
  }
  const noticeLabel = planWorkflowNoticeLabel(notice, msg);
  return noticeLabel ? `${line} · ${noticeLabel}` : line;
}
