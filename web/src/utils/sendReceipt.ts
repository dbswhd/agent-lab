/** Backend `send_receipt` on room turn complete (SSE `complete`). */
export type SendReceiptKind =
  | "discuss_saved"
  | "plan_updated"
  | "consensus_done"
  | "plan_clarify"
  | "plan_draft"
  | "plan_peer_review"
  | "plan_refine"
  | "plan_pending_approval"
  | "plan_approved";

const PLAN_WORKFLOW_RECEIPTS = new Set<string>([
  "plan_clarify",
  "plan_draft",
  "plan_peer_review",
  "plan_refine",
  "plan_pending_approval",
  "plan_approved",
]);

export function isPlanWorkflowSendReceipt(
  receipt: string | undefined,
): boolean {
  return receipt != null && PLAN_WORKFLOW_RECEIPTS.has(receipt);
}

/** Maps SSE / run.json receipt + fallbacks to composer chip copy. */
export function sendReceiptLabel(
  receipt: string | undefined,
  planLaneFallback: boolean,
  stopped: boolean,
  locale: "en" | "ko" = "ko",
): string {
  const ko = locale === "ko";
  if (stopped) return ko ? "답변 중지됨 · 부분 저장" : "Stopped · partial save";
  if (receipt === "plan_clarify") {
    return ko ? "Plan workflow · Clarify 진행" : "Plan workflow · Clarify";
  }
  if (receipt === "plan_draft") {
    return ko ? "Plan workflow · Draft 작성" : "Plan workflow · Draft";
  }
  if (receipt === "plan_peer_review") {
    return ko ? "Plan workflow · Peer review" : "Plan workflow · Peer review";
  }
  if (receipt === "plan_refine") {
    return ko ? "Plan workflow · Refine" : "Plan workflow · Refine";
  }
  if (receipt === "plan_pending_approval") {
    return ko ? "Plan 승인 대기" : "Plan pending approval";
  }
  if (receipt === "plan_approved") {
    return ko
      ? "Plan 승인됨 · execute 준비"
      : "Plan approved · ready to execute";
  }
  if (receipt === "plan_updated") return ko ? "plan 갱신됨" : "Plan updated";
  if (receipt === "consensus_done")
    return ko ? "합의 완료" : "Consensus reached";
  if (receipt === "discuss_saved")
    return ko ? "토론 저장됨" : "Discussion saved";
  return planLaneFallback
    ? ko
      ? "plan 갱신됨"
      : "Plan updated"
    : ko
      ? "토론 저장됨"
      : "Discussion saved";
}

/** Hide generic plan toasts on chat tab; show plan-workflow phase receipts. */
export function shouldShowSendReceiptOnChatTab(
  label: string | null,
  receipt?: string,
): boolean {
  if (!label) return false;
  if (isPlanWorkflowSendReceipt(receipt)) return true;
  if (label.toLowerCase().includes("plan")) return false;
  return true;
}
