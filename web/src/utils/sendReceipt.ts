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
  locale: "en" | "ko" = "ko",
): string {
  const ko = locale === "ko";
  if (stopped) return ko ? "답변 중지됨 · 부분 저장" : "Stopped · partial save";
  if (receipt === "plan_updated") return ko ? "plan 갱신됨" : "Plan updated";
  if (receipt === "consensus_done") return ko ? "합의 완료" : "Consensus reached";
  if (receipt === "discuss_saved") return ko ? "토론 저장됨" : "Discussion saved";
  return fallbackMode === "plan"
    ? ko
      ? "plan 갱신됨"
      : "Plan updated"
    : ko
      ? "토론 저장됨"
      : "Discussion saved";
}

/** Hide plan-centric toasts on the chat tab (plan tab has its own toolbar). */
export function shouldShowSendReceiptOnChatTab(label: string | null): boolean {
  if (!label) return false;
  if (label.includes("plan")) return false;
  return true;
}
