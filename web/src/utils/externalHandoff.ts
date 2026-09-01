import type { PlanExecutionRecord } from "../api/client";

export type ExternalHandoffView = NonNullable<
  PlanExecutionRecord["external_handoff"]
>;

export const DELEGATE_TOOL_IDS = {
  codex: "external:codex-delegate",
  claude: "external:claude-delegate",
} as const;

export function externalHandoffBadgeLabel(
  handoff: ExternalHandoffView | null | undefined,
): string | null {
  if (!handoff?.evidence_summary) return null;
  const clean = handoff.stopped_cleanly !== false;
  const suffix = clean ? "" : " (unclean stop)";
  const toolId = (handoff.tool_id ?? "").toLowerCase();
  const source = (handoff.source ?? "").toLowerCase();
  if (toolId.includes("codex-delegate") || source.includes("codex-delegate")) {
    return `Codex delegate${suffix}`;
  }
  if (
    toolId.includes("claude-delegate") ||
    source.includes("claude-delegate")
  ) {
    return `Claude delegate${suffix}`;
  }
  if (source === "gjc" || toolId.includes("gjc")) {
    return `GJC handoff${suffix}`;
  }
  return `External handoff${suffix}`;
}

export function externalHandoffChecksSummary(
  handoff: ExternalHandoffView | null | undefined,
): string | null {
  const checks = handoff?.checks;
  if (!checks?.length) return null;
  const passed = checks.filter((row) => Number(row.exit ?? 1) === 0).length;
  return `Checks ${passed}/${checks.length}`;
}

export function buildDelegatePrompt(args: {
  what?: string;
  where?: string;
  verify?: string;
}): string {
  const lines = [
    "Implement exactly one approved plan action in this worktree.",
    args.what ? `- 무엇을: ${args.what}` : null,
    args.where ? `- 어디서: ${args.where}` : null,
    args.verify ? `- 검증: ${args.verify}` : null,
    "",
    "When finished, print ONLY a JSON object with keys:",
    "stopped_cleanly, changed_files, checks, evidence_summary, risks.",
  ].filter(Boolean);
  return lines.join("\n");
}
