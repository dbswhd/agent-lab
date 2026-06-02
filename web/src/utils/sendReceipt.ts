import type { ComposeMode } from "./composeMode";

/** Backend `send_receipt` on room turn complete (SSE `complete`). */
export type SendReceiptKind =
  | "discuss_saved"
  | "plan_updated"
  | "consensus_done";

/** Maps SSE / run.json receipt + fallbacks to composer chip copy. */
export function sendReceiptLabel(
  receipt: string | undefined,
  fallbackMode: ComposeMode,
  stopped: boolean,
): string {
  if (stopped) return "답변 중지됨 · 부분 저장";
  if (receipt === "plan_updated") return "plan 갱신됨";
  if (receipt === "consensus_done") return "합의 완료";
  if (receipt === "discuss_saved") return "토론 저장됨";
  return fallbackMode === "plan" ? "plan 갱신됨" : "토론 저장됨";
}

/** Hide plan-centric toasts on the chat tab (plan tab has its own toolbar). */
export function shouldShowSendReceiptOnChatTab(label: string | null): boolean {
  if (!label) return false;
  if (label.includes("plan")) return false;
  return true;
}
