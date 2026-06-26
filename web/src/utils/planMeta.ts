import { agentLabel } from "./transcript";
import {
  agreementPlanSyncedLabel,
  agreementPlanSyncFailedLabel,
  latestPendingConsensusAgreement,
  type ConsensusAgreementRow,
} from "./consensusAgreement";

export type PlanUpdateMeta = {
  ts?: string;
  trigger?: string;
  mode?: string;
  synthesize_only?: boolean;
  request_id?: string;
  started_at?: string;
  completed_at?: string;
  agents?: string[];
  message_count?: number;
  chat_from_line?: number;
  chat_to_line?: number;
  status?: string;
  consensus_excerpt?: string;
  plan_sync_summary?: string;
};

export type PlanFreshness = "current" | "sync_failed" | "unknown";

export type PlanMetaView = {
  lastUpdate: PlanUpdateMeta | null;
  freshness: PlanFreshness;
  triggerLabel: string;
  timeLabel: string;
  agentsLabel: string;
  freshnessLabel: string;
  reviewTurnLabel: string | null;
  turnRolesLabel: string | null;
  pendingAgreement: ConsensusAgreementRow | null;
  chatLineLabel: string | null;
};

function triggerLabel(trigger?: string, synthesizeOnly?: boolean): string {
  if (synthesizeOnly || trigger === "synthesize_only") return "지금 정리";
  if (trigger === "consensus_reached") return "합의 후 자동 정리";
  if (trigger === "auto_turn") return "턴 후 자동 정리";
  if (trigger === "verified_loop_done") return "Verified 후 자동 정리";
  if (trigger === "execute_advance") return "실행 후 plan 갱신";
  if (trigger === "plan_turn") return "정리 후 전송";
  return trigger || "알 수 없음";
}

function formatTime(iso?: string): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function reviewTurnLabel(
  run: Record<string, unknown> | undefined,
): string | null {
  const turns = (run?.turns as Record<string, unknown>[] | undefined) ?? [];
  const reviewTurns = turns.filter((t) => t.review_mode === true);
  if (reviewTurns.length === 0) return null;
  const last = reviewTurns[reviewTurns.length - 1];
  const advocate = last.review_advocate as string | undefined;
  return advocate
    ? `쟁점 검토 · 반박 ${agentLabel(advocate)}`
    : "쟁점 검토 턴 포함";
}

/** Composer plan-stale banner when consensus or verified needs auto plan sync. */
export function composerPlanStaleNotice(
  run: Record<string, unknown> | undefined,
): string | null {
  const pending = latestPendingConsensusAgreement(run);
  if (pending?.excerpt) {
    return agreementPlanSyncFailedLabel(
      pending.excerpt,
      "plan.md 자동 정리 중…",
    );
  }
  const loop =
    (run?.verified_loop as Record<string, unknown> | undefined) ?? {};
  const sync =
    (run?.verified_plan_sync as Record<string, unknown> | undefined) ?? {};
  if (
    loop.status === "done" &&
    loop.verified_at &&
    sync.verified_at !== loop.verified_at
  ) {
    const loopGoal =
      (loop.loop_goal as Record<string, unknown> | undefined) ?? {};
    const excerpt = String(loopGoal.text ?? "Verified loop").slice(0, 80);
    return agreementPlanSyncFailedLabel(excerpt, "plan.md 자동 정리 중…");
  }
  return null;
}

const ROLE_LABELS: Record<string, string> = {
  proposer: "제안자",
  critic: "검토자",
  synthesizer: "합성자",
  executor: "실행자",
};

function formatTurnRoles(roles: Record<string, string>): string | null {
  const entries = Object.entries(roles).filter(([, role]) => role);
  if (entries.length === 0) return null;
  return entries
    .map(([agent, role]) => `${agentLabel(agent)}: ${ROLE_LABELS[role] ?? role}`)
    .join(" · ");
}

/** Extract role assignments from the latest turn snapshot, or {} if none. */
export function latestTurnRoles(
  run: Record<string, unknown> | undefined,
): Record<string, string> {
  const turns = (run?.turns as Record<string, unknown>[] | undefined) ?? [];
  for (let i = turns.length - 1; i >= 0; i--) {
    const roles = turns[i]?.roles;
    if (roles && typeof roles === "object") {
      return roles as Record<string, string>;
    }
  }
  return {};
}

export function workPlanMetaLine(meta: PlanMetaView): string | null {
  if (!meta.lastUpdate) return null;
  if (meta.pendingAgreement) return null;
  const parts: string[] = [];
  if (meta.timeLabel && meta.timeLabel !== "—") {
    parts.push(meta.timeLabel);
  }
  if (meta.triggerLabel && meta.triggerLabel !== "알 수 없음") {
    parts.push(meta.triggerLabel);
  }
  return parts.length > 0 ? parts.join(" · ") : null;
}

export function buildPlanMetaView(
  run: Record<string, unknown> | undefined,
): PlanMetaView {
  const lastUpdate =
    (run?.last_plan_update as PlanUpdateMeta | undefined) ?? null;
  const pendingAgreement = latestPendingConsensusAgreement(run);
  const trigger = triggerLabel(
    lastUpdate?.trigger,
    lastUpdate?.synthesize_only,
  );
  const timeLabel = formatTime(
    lastUpdate?.completed_at || lastUpdate?.ts || lastUpdate?.started_at,
  );
  const agents = lastUpdate?.agents ?? [];
  const agentsLabel = agents.length > 0 ? agents.join(", ") : "—";

  let chatLineLabel: string | null = null;
  if (
    typeof lastUpdate?.chat_from_line === "number" &&
    typeof lastUpdate?.chat_to_line === "number"
  ) {
    chatLineLabel = `L${lastUpdate.chat_from_line}–L${lastUpdate.chat_to_line}`;
  }

  let freshness: PlanFreshness = "unknown";
  let freshnessLabel = "갱신 이력 없음";
  if (pendingAgreement?.excerpt) {
    freshness = "sync_failed";
    freshnessLabel = `[${pendingAgreement.excerpt.slice(0, 40)}…] plan 자동 정리 실패`;
  } else if (lastUpdate?.consensus_excerpt && lastUpdate?.plan_sync_summary) {
    freshness = "current";
    freshnessLabel = agreementPlanSyncedLabel(
      lastUpdate.consensus_excerpt,
      lastUpdate.plan_sync_summary,
    );
  } else if (lastUpdate?.completed_at || lastUpdate?.ts) {
    freshness = "current";
    freshnessLabel = lastUpdate.plan_sync_summary || "plan 반영 완료";
  }

  return {
    lastUpdate,
    freshness,
    triggerLabel: trigger,
    timeLabel,
    agentsLabel,
    freshnessLabel,
    reviewTurnLabel: reviewTurnLabel(run),
    turnRolesLabel: formatTurnRoles(latestTurnRoles(run)),
    pendingAgreement,
    chatLineLabel,
  };
}

export { agreementPlanSyncedLabel };
