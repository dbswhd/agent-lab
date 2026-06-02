export type ConsensusAgreementRow = {
  id?: string;
  excerpt?: string;
  status?: string;
  message_count?: number;
  ts?: string;
  plan_synced?: boolean;
  plan_synced_at?: string;
};

export function shortExcerpt(text: string, maxLen = 52): string {
  const body = (text || "").replace(/\s+/g, " ").trim();
  if (!body) return "합의 사항";
  if (body.length <= maxLen) return body;
  return `${body.slice(0, maxLen - 1).trim()}…`;
}

export function agreementTopicLabel(excerpt?: string): string {
  return shortExcerpt(excerpt || "");
}

/** Final notification after auto plan.md sync. */
export function agreementPlanSyncedLabel(
  excerpt?: string,
  summary?: string,
): string {
  const topic = agreementTopicLabel(excerpt);
  const detail = summary?.trim() ? `: ${summary.trim()}` : "";
  return `[${topic}] 합의 완료 · plan.md 반영${detail}`;
}

/** Gate bar + desktop notification title for consensus auto-scribe. */
export function consensusDryRunGateNotice(
  excerpt?: string,
  summary?: string,
  notice?: string,
): string {
  if (notice?.trim()) return notice.trim();
  return agreementPlanSyncedLabel(excerpt, summary);
}

export function consensusDryRunNotifyTitle(excerpt?: string): string {
  const topic = agreementTopicLabel(excerpt);
  return `[${topic}] plan.md 반영됨`;
}

export function consensusDryRunNotifyBody(
  summary?: string,
  actionWhat?: string,
): string {
  const parts: string[] = [];
  if (summary?.trim()) parts.push(summary.trim());
  if (actionWhat?.trim()) {
    parts.push(`추천: ${actionWhat.trim()}`);
  }
  return parts.join(" · ") || "dry-run 실행 여부를 확인하세요.";
}

type ActionLike = { what?: string; summary?: string } | null | undefined;

export function consensusDryRunActionTitle(action: ActionLike): string {
  const raw = action?.what?.trim() || action?.summary?.trim();
  if (!raw) return "";
  return raw.replace(/\s*\(ref:[^)]+\)/g, "").trim();
}

export function agreementPlanSyncFailedLabel(
  excerpt?: string,
  message?: string,
): string {
  const topic = agreementTopicLabel(excerpt);
  const detail = message?.trim() ? ` (${message.trim()})` : "";
  return `[${topic}] plan.md 자동 정리 실패${detail}`;
}

export function pendingConsensusAgreements(
  run: Record<string, unknown> | undefined,
): ConsensusAgreementRow[] {
  const rows =
    (run?.consensus_agreements as ConsensusAgreementRow[] | undefined) ?? [];
  return rows.filter((row) => !row.plan_synced && row.status === "reached");
}

export function latestPendingConsensusAgreement(
  run: Record<string, unknown> | undefined,
): ConsensusAgreementRow | null {
  const pending = pendingConsensusAgreements(run);
  return pending.length ? pending[pending.length - 1]! : null;
}
