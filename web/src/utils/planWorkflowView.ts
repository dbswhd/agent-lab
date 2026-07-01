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
    readonly id?: string;
    readonly prompt?: string;
  }[];
  readonly answers?: Readonly<Record<string, string>>;
  readonly pending_count?: number;
};

export function clarifierQuestionAnswered(
  question: { readonly id?: string },
  answers: Readonly<Record<string, string>> | undefined,
): boolean {
  const id = String(question.id ?? "").trim();
  if (!id) return false;
  return Boolean(String(answers?.[id] ?? "").trim());
}

export function pendingClarifierQuestionCount(
  interview: ClarifierInterviewLike | null | undefined,
): number {
  if (typeof interview?.pending_count === "number") {
    return interview.pending_count;
  }
  const answers = interview?.answers ?? {};
  const questions = interview?.questions ?? [];
  return questions.filter(
    (q) => q.prompt?.trim() && !clarifierQuestionAnswered(q, answers),
  ).length;
}

/** User-visible plan workflow notices (internal flags like clarity_pending excluded). */
export const COMPOSER_PLAN_WORKFLOW_NOTICES = new Set([
  "clarify_cap_reached",
  "peer_review_cap_reached",
  "plan_gate_cap_reached",
  "plan_changed_after_approval",
]);

export function isComposerPlanWorkflowNotice(notice: string | undefined): boolean {
  const normalized = notice?.trim();
  return Boolean(normalized && COMPOSER_PLAN_WORKFLOW_NOTICES.has(normalized));
}

/** CLARIFY/INTAKE only — Human Inbox pending or workflow notice (not static clarifier scaffold). */
export function hasPlanWorkflowClarifySurface(input: {
  readonly phase?: string;
  readonly inboxPendingCount: number;
  readonly notice?: string;
}): boolean {
  const phase = (input.phase ?? "").toUpperCase();
  if (phase !== "CLARIFY" && phase !== "INTAKE") return false;
  if (input.inboxPendingCount > 0) return true;
  return isComposerPlanWorkflowNotice(input.notice);
}

/** Composer clarify lane — cap/notice banners only (questions live in Human Inbox). */
export function hasPlanWorkflowClarifyNotice(input: {
  readonly phase?: string;
  readonly notice?: string;
}): boolean {
  const phase = (input.phase ?? "").toUpperCase();
  if (phase !== "CLARIFY" && phase !== "INTAKE") return false;
  return isComposerPlanWorkflowNotice(input.notice);
}

export function shouldShowPlanWorkflowComposerNotice(input: {
  readonly showBanner: boolean;
  readonly showHint: boolean;
  readonly phase?: string;
  readonly inboxPendingCount: number;
  readonly notice?: string;
}): boolean {
  if (!input.showBanner && !input.showHint) return false;
  const phase = (input.phase ?? "").toUpperCase();
  if (phase === "CLARIFY" || phase === "INTAKE") {
    return hasPlanWorkflowClarifySurface({
      phase,
      inboxPendingCount: input.inboxPendingCount,
      notice: input.notice,
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
