import type { PlanExecutionRecord } from "../api/client";

export type ExternalHandoffView = NonNullable<
  PlanExecutionRecord["external_handoff"]
>;

export const DELEGATE_TOOL_IDS = {
  codex: "external:codex-delegate",
  claude: "external:claude-delegate",
} as const;

export const DELEGATE_ALLOWLIST_HINT =
  "설정 → 플러그인 → External에서 codex-delegate 또는 claude-delegate를 켜세요.";

export function externalHandoffBadgeLabel(
  handoff: ExternalHandoffView | null | undefined,
): string | null {
  if (!handoff?.evidence_summary) return null;
  const clean = handoff.stopped_cleanly !== false;
  const suffix = clean ? "" : " (비정상 종료)";
  const toolId = (handoff.tool_id ?? "").toLowerCase();
  const source = (handoff.source ?? "").toLowerCase();
  if (toolId.includes("codex-delegate") || source.includes("codex-delegate")) {
    return `Codex 실행 결과${suffix}`;
  }
  if (
    toolId.includes("claude-delegate") ||
    source.includes("claude-delegate")
  ) {
    return `Claude 실행 결과${suffix}`;
  }
  if (source === "gjc" || toolId.includes("gjc")) {
    return `GJC handoff${suffix}`;
  }
  return `외부 실행 결과${suffix}`;
}

export function externalHandoffChecksSummary(
  handoff: ExternalHandoffView | null | undefined,
): string | null {
  const checks = handoff?.checks;
  if (!checks?.length) return null;
  const passed = checks.filter((row) => Number(row.exit ?? 1) === 0).length;
  return `검증 ${passed}/${checks.length}`;
}

export function delegateActionLabel(toolLabel: string): string {
  const lower = toolLabel.toLowerCase();
  if (lower.includes("codex")) return "Codex로 실행";
  if (lower.includes("claude")) return "Claude로 실행";
  return toolLabel;
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
