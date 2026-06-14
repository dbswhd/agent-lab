import type { VerifiedLoopRecord } from "../api/client";

export type VerifiedLoopView = {
  loop: VerifiedLoopRecord;
  proposedGoal: string;
  completionPromise: string;
  criteria: string;
  pendingApproval: boolean;
  isDone: boolean;
  isFailed: boolean;
};

export function buildVerifiedLoopView(
  run: Record<string, unknown> | undefined,
): VerifiedLoopView {
  const loop = (run?.verified_loop as VerifiedLoopRecord | undefined) ?? {};
  const proposed = loop.proposed ?? {};
  const approved = loop.loop_goal ?? {};
  const sessionGoal = run?.session_goal as { text?: string } | undefined;
  const proposedGoal = String(
    proposed.goal ?? approved.text ?? sessionGoal?.text ?? "",
  ).trim();
  const completionPromise = String(
    proposed.completion_promise ?? approved.completion_promise ?? "DONE",
  ).trim();
  const criteria = String(
    proposed.criteria ?? approved.criteria ?? proposedGoal,
  ).trim();
  const status = loop.status ?? "";
  return {
    loop,
    proposedGoal,
    completionPromise,
    criteria,
    pendingApproval: status === "pending_approval",
    isDone: status === "done",
    isFailed: status === "failed" || Boolean(loop.circuit_breaker),
  };
}
