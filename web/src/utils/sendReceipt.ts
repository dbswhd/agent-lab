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
  if (receipt === "plan_updated") return "정리 완료 · plan 갱신";
  if (receipt === "consensus_done") return "합의 완료 · plan 동기화 가능";
  if (receipt === "discuss_saved") return "토론 저장 · plan 미변경";
  return fallbackMode === "plan"
    ? "정리 완료 · plan 갱신"
    : "토론 저장 · plan 미변경";
}
