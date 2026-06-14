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
