import { agentLabel } from "./transcript";

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
};

export type PlanFreshness = "current" | "stale" | "unknown";

export type PlanMetaView = {
  lastUpdate: PlanUpdateMeta | null;
  freshness: PlanFreshness;
  triggerLabel: string;
  timeLabel: string;
  agentsLabel: string;
  freshnessLabel: string;
  reviewTurnLabel: string | null;
  /** Chat lines added after last plan update (run.message_count − last_plan_update.message_count). */
  messagesSincePlan: number | null;
  /** chat.jsonl line range covered by last plan update (1-based). */
  chatLineLabel: string | null;
};

function triggerLabel(trigger?: string, synthesizeOnly?: boolean): string {
  if (synthesizeOnly || trigger === "synthesize_only") return "지금 정리";
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

function lastDiscussTs(run: Record<string, unknown> | undefined): string | null {
  const turns = (run?.turns as Record<string, unknown>[] | undefined) ?? [];
  for (let i = turns.length - 1; i >= 0; i -= 1) {
    const t = turns[i];
    if (t.mode === "discuss") {
      return (t.ts as string) || (t.completed_at as string) || null;
    }
  }
  return null;
}

function reviewTurnLabel(run: Record<string, unknown> | undefined): string | null {
  const turns = (run?.turns as Record<string, unknown>[] | undefined) ?? [];
  const reviewTurns = turns.filter((t) => t.review_mode === true);
  if (reviewTurns.length === 0) return null;
  const last = reviewTurns[reviewTurns.length - 1];
  const advocate = last.review_advocate as string | undefined;
  return advocate
    ? `쟁점 검토 · 반박 ${agentLabel(advocate)}`
    : "쟁점 검토 턴 포함";
}

export function buildPlanMetaView(
  run: Record<string, unknown> | undefined,
): PlanMetaView {
  const lastUpdate =
    (run?.last_plan_update as PlanUpdateMeta | undefined) ?? null;
  const runMessageCount =
    typeof run?.message_count === "number" ? run.message_count : null;
  const trigger = triggerLabel(
    lastUpdate?.trigger,
    lastUpdate?.synthesize_only,
  );
  const timeLabel = formatTime(
    lastUpdate?.completed_at || lastUpdate?.ts || lastUpdate?.started_at,
  );
  const agents = lastUpdate?.agents ?? [];
  const agentsLabel =
    agents.length > 0 ? agents.join(", ") : "—";

  let chatLineLabel: string | null = null;
  if (
    typeof lastUpdate?.chat_from_line === "number" &&
    typeof lastUpdate?.chat_to_line === "number"
  ) {
    chatLineLabel = `L${lastUpdate.chat_from_line}–L${lastUpdate.chat_to_line}`;
  }

  let freshness: PlanFreshness = "unknown";
  let freshnessLabel = "갱신 이력 없음";
  let messagesSincePlan: number | null = null;
  if (lastUpdate?.completed_at || lastUpdate?.ts) {
    const planTs = new Date(
      (lastUpdate.completed_at || lastUpdate.ts) as string,
    ).getTime();
    const discussTsRaw = lastDiscussTs(run);
    if (!discussTsRaw) {
      freshness = "current";
      freshnessLabel = "토론 이후 미갱신 없음";
    } else {
      const discussTs = new Date(discussTsRaw).getTime();
      if (discussTs > planTs) {
        freshness = "stale";
        freshnessLabel = "마지막 토론 이후 plan 미갱신";
        const planMc =
          typeof lastUpdate.message_count === "number"
            ? lastUpdate.message_count
            : null;
        if (runMessageCount != null && planMc != null) {
          messagesSincePlan = Math.max(0, runMessageCount - planMc);
        }
      } else {
        freshness = "current";
        freshnessLabel = "최신 plan";
      }
    }
  }

  return {
    lastUpdate,
    freshness,
    triggerLabel: trigger,
    timeLabel,
    agentsLabel,
    freshnessLabel,
    reviewTurnLabel: reviewTurnLabel(run),
    messagesSincePlan,
    chatLineLabel,
  };
}
