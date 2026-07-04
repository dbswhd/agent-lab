import { apiJson as json } from "./http";

// ── Mission OS (gateway, schedules, daemon, templates) ─────────────────────

export type GatewayOutboundSettings = {
  enabled?: boolean;
  urls?: string[];
  events?: string[];
  secret_set?: boolean;
  timeout_s?: number;
};

export type GatewayTelegramSettings = {
  enabled?: boolean;
  bot_token_set?: boolean;
  allowed_chat_ids?: number[];
};

export type GatewayDiscordSettings = {
  webhook_url_set?: boolean;
  allowed_channel_ids?: string[];
};

export type GatewaySlackSettings = {
  enabled?: boolean;
  webhook_url_set?: boolean;
  bot_token_set?: boolean;
  signing_secret_set?: boolean;
  allow_ingress_without_webhook?: boolean;
  allowed_channel_ids?: string[];
};

export type GatewayHybridSettings = {
  enabled?: boolean;
  relay_url?: string | null;
  relay_secret_set?: boolean;
  relay_when?: string;
  timeout_s?: number;
};

export type GatewayAdapterInfo = {
  id: string;
  channel?: string;
  enabled?: boolean;
  description?: string;
  ingress?: boolean;
  egress?: boolean;
};

export type GatewaySettingsPayload = {
  outbound?: GatewayOutboundSettings;
  telegram?: GatewayTelegramSettings;
  discord?: GatewayDiscordSettings;
  slack?: GatewaySlackSettings;
  hybrid?: GatewayHybridSettings;
  adapters?: GatewayAdapterInfo[];
  enabled?: string[];
};

export type DaemonHealthPayload = {
  ok: boolean;
  pid?: number | null;
  started_at?: string | null;
  scheduler_enabled?: boolean;
  last_scheduler_tick_at?: string | null;
  gateway?: GatewaySettingsPayload;
};

export type MissionScheduleEntry = {
  id: string;
  cron: string;
  tz?: string;
  template_id?: string | null;
  gate_profile?: "dev" | "assistant";
  sandbox?: boolean;
  enabled?: boolean;
  notify?: { on_start?: boolean };
  pre_approved_at?: string | null;
  pre_approved_by?: string | null;
  last_run_date?: string | null;
  last_run_at?: string | null;
  last_run_status?: string | null;
  last_run_error?: string | null;
  last_failed_at?: string | null;
};

export type MissionTemplateSummary = {
  id: string;
  path?: string;
  hash_match?: boolean;
  topic?: string;
  meta?: Record<string, unknown>;
};

export function fetchGatewaySettings() {
  return json<GatewaySettingsPayload>("/api/settings/gateway");
}

export function patchGatewaySettings(body: Record<string, unknown>) {
  return json<GatewaySettingsPayload & { ok?: boolean }>(
    "/api/settings/gateway",
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
  );
}

export function pingGateway() {
  return json<{ ok: boolean; delivered?: number }>(
    "/api/settings/gateway/ping",
    {
      method: "POST",
    },
  );
}

export function fetchDaemonHealth() {
  return json<DaemonHealthPayload>("/api/health/daemon");
}

export function fetchMissionTemplates() {
  return json<{ templates: MissionTemplateSummary[] }>("/api/templates");
}

export function fetchSessionSchedules(sessionId: string) {
  return json<{ session_id: string; schedules: MissionScheduleEntry[] }>(
    `/api/sessions/${encodeURIComponent(sessionId)}/schedules`,
  );
}

export function patchSessionSchedules(
  sessionId: string,
  schedules: MissionScheduleEntry[],
) {
  return json<{ ok: boolean; schedules: MissionScheduleEntry[] }>(
    `/api/sessions/${encodeURIComponent(sessionId)}/schedules`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ schedules }),
    },
  );
}

export function approveSessionSchedule(sessionId: string, scheduleId: string) {
  return json<{ ok: boolean; schedules: MissionScheduleEntry[] }>(
    `/api/sessions/${encodeURIComponent(sessionId)}/schedules/${encodeURIComponent(scheduleId)}/approve`,
    { method: "POST" },
  );
}

export function deleteSessionSchedule(sessionId: string, scheduleId: string) {
  return json<{ ok: boolean; schedules: MissionScheduleEntry[] }>(
    `/api/sessions/${encodeURIComponent(sessionId)}/schedules/${encodeURIComponent(scheduleId)}`,
    { method: "DELETE" },
  );
}

export function applySessionTemplate(sessionId: string, templateId: string) {
  return json<{ ok: boolean; fast_path?: boolean }>(
    `/api/sessions/${encodeURIComponent(sessionId)}/templates/apply`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ template_id: templateId }),
    },
  );
}

export type TrustBudgetPayload = {
  auto_merge_remaining: number;
  auto_merge_total: number;
  classifier_allow: string[];
};

export type AutoMergeEligibilityPayload = {
  eligible: boolean;
  gate_profile: string;
  reason?: string | null;
  pending_execution_id?: string | null;
  trust_budget?: TrustBudgetPayload;
};

export function fetchAutoMergeEligibility(
  sessionId: string,
  executionId?: string,
) {
  const q = executionId
    ? `?execution_id=${encodeURIComponent(executionId)}`
    : "";
  return json<AutoMergeEligibilityPayload>(
    `/api/sessions/${encodeURIComponent(sessionId)}/auto-merge/eligibility${q}`,
  );
}

export function postAutoMerge(sessionId: string, executionId: string) {
  return json<{ ok: boolean; execution?: Record<string, unknown> }>(
    `/api/sessions/${encodeURIComponent(sessionId)}/auto-merge`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ execution_id: executionId }),
    },
  );
}

export type SkillDraftSummary = {
  id: string;
  name?: string;
  path?: string;
  status?: string;
  created_at?: string;
};
