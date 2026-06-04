import type { PlanExecutionRecord } from "../api/client";

export type StoredPlanAction = {
  action_id?: string;
  index?: number;
  kind?: string;
  what?: string;
  where?: string;
  verify?: string;
};

export function actionSectionLabel(kind: string | undefined): string {
  switch (kind) {
    case "now":
      return "지금 실행";
    case "roadmap":
      return "이후";
    case "legacy":
      return "다음에 할 일";
    default:
      return "실행";
  }
}

function stripPlanRefs(text: string): string {
  return text.replace(/\s*\(ref:[^)]+\)/g, "").trim();
}

export function resolveExecutionAction(
  row: PlanExecutionRecord,
  actions: StoredPlanAction[],
): StoredPlanAction | null {
  if (row.action_what?.trim()) {
    return {
      what: row.action_what,
      where: row.action_where,
      verify: row.action_verify,
      kind: row.action_kind,
      index: row.action_index,
    };
  }
  if (row.action_id) {
    const byId = actions.find((a) => a.action_id === row.action_id);
    if (byId) return byId;
  }
  const kind = row.action_kind;
  const index = row.action_index;
  if (kind && index != null) {
    return actions.find((a) => a.kind === kind && a.index === index) ?? null;
  }
  return null;
}

function executionStatusSuffix(status: string | undefined): string | null {
  switch (status) {
    case "merged":
      return "merged";
    case "merge_conflict":
      return "conflict";
    case "rejected":
      return "rejected";
    case "superseded":
      return "revised";
    case "completed":
      return "done";
    case "review_required":
      return "review";
    case "failed":
      return "failed";
    default:
      return null;
  }
}

export function executionHistoryBadge(row: PlanExecutionRecord): string {
  const section = actionSectionLabel(row.action_kind);
  const base = `${section} #${row.action_index ?? "?"}`;
  const suffix = executionStatusSuffix(row.status);
  return suffix ? `${base} · ${suffix}` : base;
}

export function executionHistoryTitle(
  row: PlanExecutionRecord,
  action: StoredPlanAction | null,
): string {
  const raw =
    action?.what?.trim() ||
    row.action_what?.trim() ||
    row.draft_summary?.split("\n").find((line) => line.trim())?.trim();
  if (raw) return stripPlanRefs(raw);
  return executionHistoryBadge(row);
}

export function executionContextFields(
  row: PlanExecutionRecord,
  action: StoredPlanAction | null,
): { where?: string; verify?: string; workspaceLabel?: string } {
  const where = action?.where?.trim() || row.action_where?.trim();
  const verify = action?.verify?.trim() || row.action_verify?.trim();
  const workspaceLabel = row.workspace_label?.trim();
  return {
    where: where || undefined,
    verify: verify || undefined,
    workspaceLabel: workspaceLabel || undefined,
  };
}

export function formatExecutionTime(iso?: string | null): string {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleString("ko-KR", {
      month: "numeric",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return "";
  }
}
