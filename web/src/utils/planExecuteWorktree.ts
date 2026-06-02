import type { PlanExecutionRecord } from "../api/client";

export function isWorktreeExecution(
  row: PlanExecutionRecord | null | undefined,
): boolean {
  return row?.isolation_effective === "worktree";
}

export function isActiveExecution(
  row: PlanExecutionRecord | null | undefined,
): boolean {
  const status = row?.status;
  return status === "pending_approval" || status === "merge_conflict";
}

export function findActiveExecution(
  executions: PlanExecutionRecord[] | undefined,
): PlanExecutionRecord | null {
  if (!executions?.length) return null;
  return (
    [...executions]
      .reverse()
      .find((row) => isActiveExecution(row)) ?? null
  );
}

export function executionApproveLabel(
  row: PlanExecutionRecord | null | undefined,
): string {
  if (isWorktreeExecution(row)) return "Merge 승인";
  if (row?.isolation_effective === "apply") return "파일 반영";
  return "승인 (변경 유지)";
}

export function executionRejectLabel(
  row: PlanExecutionRecord | null | undefined,
): string {
  if (isWorktreeExecution(row)) return "Merge 거부 (worktree 폐기)";
  if (row?.isolation_effective === "apply") return "거부 (되돌리기)";
  return "거부 (되돌리기)";
}

export function worktreeBannerLines(
  row: PlanExecutionRecord,
): { branch?: string; worktree?: string; base?: string; commit?: string } {
  return {
    branch: row.exec_branch?.trim() || undefined,
    worktree: row.worktree_path?.trim() || undefined,
    base: row.base_branch?.trim() || undefined,
    commit: row.exec_commit_sha?.trim() || undefined,
  };
}

export function mergeConflictFiles(row: PlanExecutionRecord): string[] {
  const files = row.merge?.conflict_files;
  return Array.isArray(files) ? files.filter(Boolean) : [];
}

export function mergedCommitSha(row: PlanExecutionRecord): string | null {
  const sha = row.merge?.commit_sha;
  return sha?.trim() ? sha.trim() : null;
}
