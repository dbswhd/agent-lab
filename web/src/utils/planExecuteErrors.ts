import {
  PlanExecuteDryRunError,
  PlanSnapshotRequiredError,
  type PreVerifyRecord,
} from "../api/client";

export function formatPlanExecuteError(err: unknown): string {
  if (err instanceof PlanSnapshotRequiredError) {
    return "plan 스냅샷 승인이 필요합니다.";
  }
  if (err instanceof PlanExecuteDryRunError) {
    const parts = [err.message];
    if (err.remediation?.length) {
      parts.push(err.remediation.join(" · "));
    }
    return parts.filter(Boolean).join(" — ");
  }
  if (err && typeof err === "object" && "preVerify" in err) {
    const fb = (err as Error & { preVerify?: PreVerifyRecord }).preVerify
      ?.feedback;
    if (fb) return `pre_execute: ${fb}`;
  }
  if (err instanceof Error) return err.message;
  return String(err);
}
