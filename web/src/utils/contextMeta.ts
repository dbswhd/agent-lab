/** Types and formatters for run.json turn context (ContextBundle meta). */

export type ContextLayerChars = Record<string, number>;

export type AgentContextMeta = {
  agent: string;
  parallel_round?: number;
  model?: string;
  turns_omitted?: number;
  chars_omitted?: number;
  peer_message_count?: number;
  peer_deduped?: number;
  pinned_message_count?: number;
  layer_chars?: ContextLayerChars;
  limits?: {
    max_thread_chars?: number;
    recent_turns?: number;
    warn_budget_pct?: number;
    critical_budget_pct?: number;
  };
  budget_pct?: number;
  trim_level?: "ok" | "warn" | "critical" | string;
  messages_in_payload?: number;
  messages_in_turn?: number;
  messages_in_session?: number;
  numbered_context?: boolean;
  line_range?: string;
};

export type TurnContextSummary = {
  agent_count?: number;
  payload_chars_max?: number;
  payload_chars_total?: number;
  trim_level?: string;
  max_thread_chars?: number;
  any_turns_omitted?: boolean;
  any_chars_omitted?: boolean;
};

export type TurnContextBlock = {
  agents?: AgentContextMeta[];
  summary?: TurnContextSummary;
  payload_chars_total?: number;
  models?: Record<string, string>;
};

const LAYER_LABELS: Record<string, string> = {
  constraints: "constraints",
  plan_open: "plan 미결",
  bridge: "R1 bridge",
  recent: "최근 N턴",
  peer: "동료 발화",
  guidance: "guidance",
  connect_hint: "connect",
  claude_tools: "Claude tools",
  follow_up: "follow-up",
};

export function layerLabel(key: string): string {
  return LAYER_LABELS[key] ?? key;
}

export function trimLevelLabel(level?: string): string {
  if (level === "critical") return "여유 부족";
  if (level === "warn") return "trim 있음";
  return "정상";
}

export function formatBudgetLine(meta: AgentContextMeta): string {
  const pct = meta.budget_pct ?? 0;
  const max = meta.limits?.max_thread_chars ?? meta.layer_chars?.total ?? 0;
  const total = meta.layer_chars?.total ?? 0;
  return `${pct}% · ${total.toLocaleString()} / ${max.toLocaleString()} chars`;
}

export function parseLastTurnContext(
  run: Record<string, unknown> | undefined,
): TurnContextBlock | null {
  const last = run?.last_turn as Record<string, unknown> | undefined;
  const ctx = last?.context as TurnContextBlock | undefined;
  return ctx ?? null;
}

export const LAYER_ORDER = [
  "constraints",
  "plan_open",
  "bridge",
  "recent",
  "peer",
  "guidance",
  "connect_hint",
  "claude_tools",
  "follow_up",
] as const;
