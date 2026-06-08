import { isTauri } from "@tauri-apps/api/core";

export type BackendOption = { id: string; label: string; ready: boolean };

export type AgentOption = {
  id: string;
  label: string;
  ready: boolean;
  model?: string;
};

export type SessionSummary = {
  id: string;
  topic: string;
  created_at?: string;
  model?: string;
  archived?: boolean;
  workflow?: string;
  workspace_preset?: string;
  session_template?: string;
  workspace_label?: string;
  agents?: string[];
  workspace_path?: string;
};

export type ChatLine = {
  role: string;
  agent?: string | null;
  content: string;
  ts?: string;
  /** Parallel wave within one human message (1 = first replies, 2+ = peer discussion). */
  parallel_round?: number;
  /** human = default UI; peer = coordination channel (digest / echoed headers). */
  visibility?: "human" | "peer";
};

export type RoomObjection = {
  id: string;
  from: string;
  act: "BLOCK" | "CHALLENGE";
  body: string;
  status: "open" | "resolved_accepted" | "resolved_wontfix";
  turn?: number;
  target_ref?: string;
  task_id?: string;
  plan_action_index?: number;
  ts?: string;
};

export type RoomTask = {
  id: string;
  title: string;
  status: "pending" | "in_progress" | "completed" | "cancelled" | "blocked";
  owner_agent?: string | null;
  depends_on?: string[];
  source?: string;
  plan_action_index?: number;
  plan_action_id?: string;
  endorsements?: Record<string, string>;
};

export type RoomArtifact = {
  id: string;
  producer: string;
  kind: "log" | "diff" | "table" | "file_ref" | "delegate";
  summary?: string;
  path?: string;
  turn?: number;
  parallel_round?: number;
  refs?: string[];
  ts?: string;
};

export type PreVerifyRecord = {
  event?: string;
  blocked?: boolean;
  feedback?: string;
  exit_code?: number;
  command?: string;
};

export type MailboxMessage = {
  id: string;
  from: string;
  to: string;
  body: string;
  task_id?: string;
  human_turn?: number;
  parallel_round?: number;
  ts: string;
  read?: boolean;
};

export type ConsensusGateBlockedTask = {
  id: string;
  title: string;
  endorsements: number;
};

export type ConsensusGatePayload = {
  required_endorsements: number;
  active_agent_count: number;
  blocked_tasks: ConsensusGateBlockedTask[];
};

export type RoomTasksPayload = {
  team_lead: string;
  turn_leads?: Record<string, string>;
  /** Active room agents — used for team-agreement denominator in the task bar. */
  agents?: string[];
  tasks: RoomTask[];
  claimable: RoomTask[];
  counts: { pending: number; in_progress: number; completed: number };
  consensus_tasks_ready?: boolean;
  consensus_task_blockers?: string[];
  consensus_gate?: ConsensusGatePayload;
  open_task_count?: number;
  mailbox?: MailboxMessage[];
  mailbox_unread?: Record<string, number>;
  objections?: RoomObjection[];
  open_objections?: RoomObjection[];
  open_objection_count?: number;
  artifacts?: RoomArtifact[];
  artifact_count?: number;
};

export type SessionObservability = {
  hook_runs_tail?: Array<Record<string, unknown>>;
  hook_run_count?: number;
  last_communicate_meta?: Record<string, unknown> | null;
};

export type SessionDetail = {
  id: string;
  topic: string;
  plan_md: string;
  transcript_md: string;
  meta: Record<string, unknown>;
  chat?: ChatLine[];
  run?: Record<string, unknown>;
  attachments?: string[];
  observability?: SessionObservability;
};

export type SessionGoalRecord = {
  text?: string;
  set_at?: string;
  updated_at?: string;
  set_by?: "human" | string;
};

export type GoalOracleCheckRecord = {
  at?: string;
  verdict?: "pass" | "fail" | string;
  detail?: string;
  source?: "mock" | "live" | string;
};

export type GoalLoopRecord = {
  enabled?: boolean;
  max_checks?: number;
  checks?: GoalOracleCheckRecord[];
  last_check?: GoalOracleCheckRecord;
  status?: "open" | "achieved" | "abandoned" | string;
  achieved_at?: string;
  auto_continue_pending?: boolean;
  continue_prompt?: string;
};

export type VerifiedLoopProposal = {
  goal?: string;
  completion_promise?: string;
  criteria?: string;
  proposed_at?: string;
  source?: string;
};

export type VerifiedLoopGoal = {
  text?: string;
  completion_promise?: string;
  criteria?: string;
  approved_at?: string;
  approved_by?: string;
};

export type VerifiedLoopCheck = {
  at?: string;
  verdict?: "verified" | "fail" | string;
  detail?: string;
  source?: string;
  oracle_session_id?: string;
};

export type VerifiedLoopRecord = {
  status?:
    | "proposing"
    | "pending_approval"
    | "running"
    | "done"
    | "failed"
    | "cancelled"
    | string;
  proposed?: VerifiedLoopProposal;
  loop_goal?: VerifiedLoopGoal;
  iteration?: number;
  max_iterations?: number;
  verification_attempts?: number;
  max_verification_attempts?: number;
  checks?: VerifiedLoopCheck[];
  last_check?: VerifiedLoopCheck;
  verified_at?: string;
  circuit_breaker?: boolean;
  circuit_reason?: string;
};

const API_ORIGIN = "http://127.0.0.1:8765";

export function apiBase(): string {
  const fromEnv = import.meta.env.VITE_API_BASE as string | undefined;
  if (fromEnv) return fromEnv.replace(/\/$/, "");
  // Same-origin: Vite dev proxy (1420/5173) or release app served by uvicorn (8765).
  if (typeof window !== "undefined") {
    const port = window.location.port;
    if (port === "1420" || port === "5173" || port === "8765") {
      return "";
    }
  }
  // Fallback: embedded https://tauri.localhost cannot fetch http API (WebKit mixed content).
  if (isTauri()) return API_ORIGIN;
  return "";
}

function apiUrl(path: string): string {
  const base = apiBase();
  return base ? `${base}${path}` : path;
}

async function json<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(apiUrl(path), init);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || res.statusText);
  }
  return res.json() as Promise<T>;
}

export type AgentHealthRow = {
  id: string;
  label: string;
  ready: boolean;
  configured: boolean;
  bridge: "ok" | "error" | "unknown" | "n/a";
  bridge_mode?: "external" | "auto" | "n/a";
  model?: string;
  detail?: string;
  hint?: string | null;
  reason?: string | null;
  degraded?: boolean;
  failure_code?: string | null;
  fallback?: string | null;
  remediation?: string[];
  capabilities?: string[];
  capability_label?: string;
};

export type HealthResponse = {
  ok: boolean;
  api?: { ok: boolean; port?: number };
  provider?: string;
  model?: string;
  agents: AgentHealthRow[];
  agents_ready?: string[];
  sessions_dir?: string;
};

export function fetchHealth(probeBridge = false, probePreflight = false) {
  const params = new URLSearchParams();
  if (probeBridge) params.set("probe_bridge", "true");
  if (probePreflight) params.set("probe_preflight", "true");
  const q = params.toString() ? `?${params.toString()}` : "";
  return json<HealthResponse>(`/api/health${q}`);
}

export type CredentialProviderId = "cursor" | "claude" | "codex";

export type AgentCredentialRow = {
  id: CredentialProviderId;
  label: string;
  env_primary: string;
  env_fallback: string;
  primary_label: string;
  fallback_label: string;
  has_primary: boolean;
  has_fallback: boolean;
  primary_masked: string | null;
  fallback_masked: string | null;
  stored_primary: boolean;
  stored_fallback: boolean;
};

export type CredentialsResponse = {
  ok: boolean;
  path: string;
  agents: AgentCredentialRow[];
  saved?: boolean;
};

export type CredentialSlotPatch = {
  primary?: string;
  fallback?: string;
  primary_label?: string;
  fallback_label?: string;
};

export type CredentialsPatch = Partial<
  Record<CredentialProviderId, CredentialSlotPatch>
>;

export function fetchCredentials() {
  return json<CredentialsResponse>("/api/settings/credentials");
}

export function putCredentials(patch: CredentialsPatch) {
  return json<CredentialsResponse>("/api/settings/credentials", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
}

export type MissionPhase =
  | "MISSION_DEFINE"
  | "MISSION_PAUSED"
  | "DISCUSS"
  | "PLAN_GATE"
  | "PLAN_REJECT"
  | "EXECUTE_QUEUE"
  | "DRY_RUN"
  | "MERGE_REVIEW"
  | "VERIFY"
  | "REPAIR"
  | "MISSION_DONE";

export type MissionLoopState = {
  enabled: boolean;
  phase: MissionPhase;
  iteration?: number;
  pending_action_indices?: number[];
  current_action_index?: number | null;
  circuit_breaker?: boolean;
  circuit_breaker_reason?: string | null;
  plan_gate?: {
    status?: string;
    momus_round?: number;
    max_momus_rounds?: number;
  };
  autonomous_segment?: { active?: boolean };
};

export type ContextLayersState = {
  mission_wisdom: boolean;
  repo_tree: boolean;
};

export type ContextLayersResponse = {
  ok: boolean;
  session_id?: string;
  context_layers: ContextLayersState;
};

export function fetchContextLayers(sessionId: string) {
  return json<ContextLayersResponse>(
    `/api/sessions/${encodeURIComponent(sessionId)}/context-layers`,
  );
}

export function patchContextLayers(
  sessionId: string,
  patch: Partial<ContextLayersState>,
) {
  return json<ContextLayersResponse>(
    `/api/sessions/${encodeURIComponent(sessionId)}/context-layers`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(patch),
    },
  );
}

export type MissionNotepadSummary = {
  file: string;
  lines: number;
  preview: string;
  path?: string;
};

export type MissionLoopResponse = {
  ok: boolean;
  enabled: boolean;
  mission_loop: MissionLoopState;
  has_loop_goal?: boolean;
  verified_loop_status?: string | null;
  notepads?: MissionNotepadSummary[];
};

export function fetchMissionLoop(sessionId: string) {
  return json<MissionLoopResponse>(
    `/api/sessions/${encodeURIComponent(sessionId)}/mission-loop`,
  );
}

export function enableMissionLoop(
  sessionId: string,
  startAutonomous = true,
) {
  return json<MissionLoopResponse>(
    `/api/sessions/${encodeURIComponent(sessionId)}/mission-loop/enable`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ start_autonomous: startAutonomous }),
    },
  );
}

export function advanceMissionLoop(
  sessionId: string,
  opts?: { permissions?: Record<string, unknown>; executor?: string },
) {
  return json<MissionLoopResponse & { advance?: Record<string, unknown> }>(
    `/api/sessions/${encodeURIComponent(sessionId)}/mission-loop/advance`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        permissions: opts?.permissions,
        executor: opts?.executor,
      }),
    },
  );
}

export function pauseMissionLoop(
  sessionId: string,
  opts?: { reason?: string; cleanupExecutions?: boolean },
) {
  return json<MissionLoopResponse & { pause?: Record<string, unknown> }>(
    `/api/sessions/${encodeURIComponent(sessionId)}/mission-loop/pause`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        reason: opts?.reason ?? "user_cancel",
        cleanup_executions: opts?.cleanupExecutions ?? true,
      }),
    },
  );
}

export function resumeMissionLoop(sessionId: string, resumePhase = "EXECUTE_QUEUE") {
  return json<MissionLoopResponse & { resume?: Record<string, unknown> }>(
    `/api/sessions/${encodeURIComponent(sessionId)}/mission-loop/resume`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ resume_phase: resumePhase }),
    },
  );
}

export function clearMissionCircuitBreaker(
  sessionId: string,
  resumePhase = "DISCUSS",
) {
  return json<MissionLoopResponse>(
    `/api/sessions/${encodeURIComponent(sessionId)}/mission-loop/clear-circuit-breaker`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ resume_phase: resumePhase }),
    },
  );
}

export type DiagnosticsResponse = {
  ok: boolean;
  pid: number;
  uptime_seconds: number;
  port: number;
  port_status: { listening: boolean; host?: string; port?: number; error?: string };
  sessions_dir: string;
  paths: Record<string, string | null>;
  agent_tools: Record<string, string | null>;
  boot_log_tail: string[];
  boot_log_path: string;
  api_log_path: string;
};

export function fetchDiagnostics() {
  return json<DiagnosticsResponse>("/api/diagnostics");
}

export function reconnectCursorBridge() {
  return json<{
    ok: boolean;
    bridge: AgentHealthRow["bridge"];
    hint?: string | null;
    agent: AgentHealthRow;
  }>("/api/health/reconnect-cursor", { method: "POST" });
}

export function fetchAgents() {
  return json<{ agents: AgentOption[]; default: string[] }>("/api/agents");
}

export function fetchBackends() {
  return json<{ default: string | null; options: BackendOption[] }>(
    "/api/backends",
  );
}

export function fetchSessionSetupOptions() {
  return json<import("../utils/sessionSetup").SessionSetupOptions>(
    "/api/session-setup/options",
  );
}

export function pickFolderViaDesktopApi(defaultPath?: string | null) {
  return json<{ available: boolean; path: string | null; cancelled: boolean }>(
    "/api/desktop/pick-folder",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        default_path: defaultPath?.trim() || null,
      }),
    },
  );
}

export function fetchSessions(archived = false) {
  const q = archived ? "?archived=true" : "";
  return json<{ sessions: SessionSummary[] }>(`/api/sessions${q}`);
}

export function archiveSession(id: string) {
  return json<{ ok: boolean }>(
    `/api/sessions/${encodeURIComponent(id)}/archive`,
    { method: "POST" },
  );
}

export function unarchiveSession(id: string) {
  return json<{ ok: boolean }>(
    `/api/sessions/${encodeURIComponent(id)}/unarchive`,
    { method: "POST" },
  );
}

export function fetchSession(id: string) {
  return json<SessionDetail>(`/api/sessions/${encodeURIComponent(id)}`);
}

export function autoSyncSessionPlan(id: string) {
  return json<{ ok: boolean; synced: boolean } & SessionDetail>(
    `/api/sessions/${encodeURIComponent(id)}/plan/auto-sync`,
    { method: "POST" },
  );
}

export function setSessionGoal(
  id: string,
  body: { text: string; max_checks?: number },
) {
  return json<{
    ok: boolean;
    session_goal: SessionGoalRecord;
    goal_loop: GoalLoopRecord;
  }>(`/api/sessions/${encodeURIComponent(id)}/goal`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function checkSessionGoal(id: string) {
  return json<{
    ok: boolean;
    checked: boolean;
    reason?: string;
    check?: GoalOracleCheckRecord;
    session_goal?: SessionGoalRecord;
    goal_loop?: GoalLoopRecord;
  }>(`/api/sessions/${encodeURIComponent(id)}/goal/check`, {
    method: "POST",
  });
}

export function approveVerifiedLoop(
  id: string,
  body?: {
    goal?: string;
    completion_promise?: string;
    criteria?: string;
  },
) {
  return json<{
    ok: boolean;
    verified_loop: VerifiedLoopRecord;
    continue_prompt?: string;
  }>(`/api/sessions/${encodeURIComponent(id)}/verified-loop/approve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body ?? {}),
  });
}

export function rejectVerifiedLoop(id: string, note = "") {
  return json<{ ok: boolean; verified_loop: VerifiedLoopRecord }>(
    `/api/sessions/${encodeURIComponent(id)}/verified-loop/reject`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ note }),
    },
  );
}

export type SlashCommandRecord = {
  id: string;
  slash: string;
  label: string;
  description?: string;
  scope?: string;
  kind: string;
  agent?: string | null;
  source?: string;
  enabled?: boolean;
  disabled_reason?: string | null;
  native_add_hint?: string;
};

export type AgentPluginRecord = {
  id: string;
  name: string;
  agent: string;
  kind: string;
  description?: string;
  status?: string;
  enabled_default?: boolean;
  native_add_hint?: string;
  slash?: string;
};

export function fetchCommands(sessionId?: string | null) {
  const q = sessionId
    ? `?session_id=${encodeURIComponent(sessionId)}`
    : "";
  return json<{
    ok: boolean;
    commands: SlashCommandRecord[];
    allowlist?: Record<string, string[]>;
    discovery_mock?: boolean;
  }>(`/api/commands${q}`);
}

export function fetchAgentPlugins(sessionId?: string | null) {
  const q = sessionId
    ? `?session_id=${encodeURIComponent(sessionId)}`
    : "";
  return json<{
    ok: boolean;
    plugins: AgentPluginRecord[];
    allowlist: Record<string, string[]>;
    agents: Record<string, AgentPluginRecord[]>;
    mock?: boolean;
  }>(`/api/agents/plugins${q}`);
}

export function patchSessionAgentPlugins(
  sessionId: string,
  body: { agent: string; enabled: string[] },
) {
  return json<{ ok: boolean; enabled: string[]; allowlist: Record<string, string[]> }>(
    `/api/sessions/${encodeURIComponent(sessionId)}/agent-plugins`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
  );
}

export function runSessionCommand(
  sessionId: string,
  body: { command_id: string; args?: string },
) {
  return json<{
    ok: boolean;
    kind: string;
    handler?: string;
    text?: string;
    detail?: string;
    result?: unknown;
    command?: SlashCommandRecord;
  }>(`/api/sessions/${encodeURIComponent(sessionId)}/commands/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function parseSlashInput(text: string): { name: string; args: string } | null {
  const trimmed = text.trim();
  if (!trimmed.startsWith("/")) return null;
  const match = /^\/([a-zA-Z0-9_-]+)(?:\s+(.*))?$/s.exec(trimmed);
  if (!match) return null;
  return { name: match[1], args: (match[2] ?? "").trim() };
}

export function matchSlashCommand(
  text: string,
  commands: SlashCommandRecord[],
): SlashCommandRecord | null {
  const parsed = parseSlashInput(text);
  if (!parsed) return null;
  const needle = parsed.name.toLowerCase();
  return (
    commands.find(
      (c) =>
        c.slash.replace(/^\//, "").toLowerCase() === needle ||
        c.id.toLowerCase() === needle ||
        c.id.toLowerCase().endsWith(`:${needle}`),
    ) ?? null
  );
}

export function fetchSessionTasks(sessionId: string) {
  return json<RoomTasksPayload>(
    `/api/sessions/${encodeURIComponent(sessionId)}/tasks`,
  );
}

export type AgentCapabilityRow = {
  tools: string[];
  cwd_role: string;
  label?: string;
  restrictions?: string[];
  cwd_path?: string;
};

export type AgentCapabilitiesResponse = {
  ok: boolean;
  agent_capabilities: Record<string, AgentCapabilityRow>;
  agent_capabilities_custom?: boolean;
  resolved_cwd?: Record<string, string>;
};

export function fetchSessionAgentCapabilities(
  sessionId: string,
  permissions?: Record<string, unknown>,
) {
  const q =
    permissions && Object.keys(permissions).length
      ? `?permissions=${encodeURIComponent(JSON.stringify(permissions))}`
      : "";
  return json<AgentCapabilitiesResponse>(
    `/api/sessions/${encodeURIComponent(sessionId)}/agent-capabilities${q}`,
  );
}

export function patchSessionAgentCapabilities(
  sessionId: string,
  capabilities: Record<string, AgentCapabilityRow>,
) {
  return json<AgentCapabilitiesResponse>(
    `/api/sessions/${encodeURIComponent(sessionId)}/agent-capabilities`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ capabilities }),
    },
  );
}

export function completeSessionTask(
  sessionId: string,
  taskId: string,
  artifactRefs?: string[],
) {
  return json<RoomTasksPayload>(
    `/api/sessions/${encodeURIComponent(sessionId)}/tasks/${encodeURIComponent(taskId)}/complete`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ artifact_refs: artifactRefs ?? [] }),
    },
  );
}

export function patchSessionTeamLead(sessionId: string, agent: string) {
  return json<RoomTasksPayload>(
    `/api/sessions/${encodeURIComponent(sessionId)}/team-lead`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ agent }),
    },
  );
}

export function resolveSessionObjection(
  sessionId: string,
  objectionId: string,
  verdict: "accepted" | "wontfix",
  note = "",
) {
  return json<RoomTasksPayload>(
    `/api/sessions/${encodeURIComponent(sessionId)}/objections/${encodeURIComponent(objectionId)}/resolve`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ verdict, note }),
    },
  );
}

function parseRoomRunHttpError(text: string): string {
  try {
    const body = JSON.parse(text) as {
      detail?: string | { message?: string; agents?: { id: string; reason: string }[] };
    };
    const detail = body.detail;
    if (detail && typeof detail === "object" && Array.isArray(detail.agents)) {
      return detail.agents.map((a) => `${a.id}: ${a.reason}`).join("; ");
    }
    if (typeof detail === "string") return detail;
  } catch {
    /* plain text */
  }
  return text;
}

async function consumeSse(
  res: Response,
  onEvent: (data: Record<string, unknown>) => void,
): Promise<boolean> {
  const reader = res.body?.getReader();
  if (!reader) throw new Error("no response body");
  const dec = new TextDecoder();
  let buf = "";
  let sawTerminal = false;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    const parts = buf.split("\n\n");
    buf = parts.pop() ?? "";
    for (const part of parts) {
      for (const line of part.split("\n")) {
        if (line.startsWith("data: ")) {
          const data = JSON.parse(line.slice(6)) as Record<string, unknown>;
          const t = String(data.type ?? "");
          if (t === "complete" || t === "error" || t === "run_failed") {
            sawTerminal = true;
          }
          onEvent(data);
        }
      }
    }
  }
  return sawTerminal;
}

export async function runGraph(
  topic: string,
  backend: string | null,
  onEvent: (data: Record<string, unknown>) => void,
): Promise<void> {
  const res = await fetch(apiUrl("/api/runs"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ topic, backend }),
  });
  if (!res.ok) throw new Error(await res.text());
  await consumeSse(res, onEvent);
}

export type RoomMode = "discuss" | "plan";

export type RunRoomOptions = {
  sessionId?: string;
  files?: File[];
  /** discuss = no scribe; plan = scribe after round. Overrides synthesize when set. */
  mode?: RoomMode;
  synthesize?: boolean;
  /** Re-synthesize plan.md from existing chat without a new agent round. */
  synthesizeOnly?: boolean;
  /** Idempotency key for synthesize-only runs (retry / refresh safe). */
  requestId?: string;
  /** Parallel agent waves per human message (2 = first replies, then peer discussion). */
  agentRounds?: number;
  permissions?: Record<string, unknown>;
  /** Turn-level devil's advocate rotation (2nd round only). */
  reviewMode?: boolean;
  /** Free discuss: loop until all peers reply 「이의 없습니다」 to anchor proposal. */
  consensusMode?: boolean;
  /** Pin cap, shorter replies, slimmer consensus payloads (subscription-friendly). */
  efficiencyMode?: boolean;
  /** Composer turn profile id (quick/analyze/free). */
  turnProfile?: string;
  /** Collect agent outputs into artifacts[] (research / specialist). */
  researchMode?: boolean;
  /** Session start workspace preset (new sessions only). */
  workspaceId?: string;
  /** User-picked folder when workspaceId is custom (new sessions only). */
  workspacePath?: string;
  /** Per-agent cwd/tools profile (run.json agent_capabilities). */
  agentCapabilities?: Record<string, AgentCapabilityRow>;
  /** Per-agent resume bindings for new sessions (session id or "new"). */
  agentThreadBindings?: Record<string, string>;
  /** Always general for now; workflow templates deferred. */
  sessionTemplate?: string;
  /** Abort in-flight SSE (UI stop). */
  signal?: AbortSignal;
};

export function renameSession(id: string, topic: string) {
  return json<{ ok: boolean; topic: string }>(
    `/api/sessions/${encodeURIComponent(id)}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ topic }),
    },
  );
}

export function deleteSession(id: string) {
  return json<{ ok: boolean }>(
    `/api/sessions/${encodeURIComponent(id)}`,
    { method: "DELETE" },
  );
}

export type ContextPreviewOptions = {
  sessionId: string;
  agent: string;
  parallelRound?: number;
  reviewMode?: boolean;
  efficiencyMode?: boolean;
  slimContext?: boolean;
  permissions?: Record<string, unknown>;
  agents?: string[];
};

export function fetchContextPreview(opts: ContextPreviewOptions) {
  return json<{
    session_id: string;
    agent: string;
    parallel_round: number;
    review_mode: boolean;
    payload: string;
    chars: number;
    meta?: import("../utils/contextMeta").AgentContextMeta;
    limits?: Record<string, unknown>;
  }>("/api/room/context-preview", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      session_id: opts.sessionId,
      agent: opts.agent,
      parallel_round: opts.parallelRound ?? 1,
      review_mode: opts.reviewMode ?? false,
      efficiency_mode: opts.efficiencyMode ?? false,
      slim_context: opts.slimContext ?? false,
      permissions: opts.permissions ?? {},
      agents: opts.agents,
    }),
  });
}

export async function runRoom(
  topic: string,
  agents: string[],
  onEvent: (data: Record<string, unknown>) => void,
  opts?: RunRoomOptions,
): Promise<void> {
  const mode = opts?.mode ?? (opts?.synthesize ? "plan" : "discuss");
  const synthesize =
    opts?.synthesize ?? (mode === "plan");
  const form = new FormData();
  form.append("topic", topic);
  form.append("agents", JSON.stringify(agents));
  form.append("mode", mode);
  form.append("synthesize", String(synthesize));
  form.append("synthesize_only", String(opts?.synthesizeOnly ?? false));
  form.append("agent_rounds", String(opts?.agentRounds ?? 1));
  form.append("review_mode", String(opts?.reviewMode ?? false));
  form.append("consensus_mode", String(opts?.consensusMode ?? false));
  form.append("efficiency_mode", String(opts?.efficiencyMode ?? false));
  form.append("turn_profile", opts?.turnProfile ?? "analyze");
  form.append("research_mode", String(opts?.researchMode ?? false));
  form.append("workspace_id", opts?.workspaceId ?? "agent-lab");
  if (opts?.workspacePath?.trim()) {
    form.append("workspace_path", opts.workspacePath.trim());
  }
  if (opts?.agentCapabilities && Object.keys(opts.agentCapabilities).length) {
    form.append(
      "agent_capabilities",
      JSON.stringify(opts.agentCapabilities),
    );
  }
  if (opts?.agentThreadBindings && Object.keys(opts.agentThreadBindings).length) {
    form.append(
      "agent_thread_bindings",
      JSON.stringify(opts.agentThreadBindings),
    );
  }
  form.append("session_template", opts?.sessionTemplate ?? "general");
  if (opts?.requestId) {
    form.append("request_id", opts.requestId);
  }
  if (opts?.sessionId) {
    form.append("session_id", opts.sessionId);
  }
  form.append("permissions", JSON.stringify(opts?.permissions ?? {}));
  for (const f of opts?.files ?? []) {
    form.append("files", f, f.name);
  }
  const res = await fetch(apiUrl("/api/room/runs"), {
    method: "POST",
    body: form,
    signal: opts?.signal,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(parseRoomRunHttpError(text));
  }
  const sawTerminal = await consumeSse(res, onEvent);
  if (!sawTerminal) {
    onEvent({
      type: "run_failed",
      message:
        "SSE 연결이 끊어졌습니다. 서버 실행 상태를 확인하거나 실행 잠금 해제를 시도하세요.",
    });
  }
}

export async function cancelRoomRun(sessionId?: string): Promise<void> {
  const res = await fetch(apiUrl("/api/room/runs/cancel"), {
    method: "POST",
    headers: sessionId ? { "Content-Type": "application/json" } : undefined,
    body: sessionId
      ? JSON.stringify({ session_id: sessionId })
      : undefined,
  });
  if (!res.ok) throw new Error(await res.text());
}

export function releaseRoomRunLock() {
  return json<{
    ok: boolean;
    released?: boolean;
    locked?: boolean;
    age_sec?: number | null;
  }>("/api/room/runs/release-lock", { method: "POST" });
}

export function fetchRoomRunLock() {
  return json<{
    ok: boolean;
    locked: boolean;
    age_sec?: number | null;
  }>("/api/room/run-lock");
}

export type ExecuteWorkspace = {
  path: string;
  label: string;
  paths_found: string[];
  paths_missing: string[];
};

export type PlanActionItem = {
  index: number;
  what: string;
  where: string;
  verify: string;
  refs: string[];
  expected_paths: string[];
  verification_paths?: string[];
  monitored_paths?: string[];
  action_key?: string;
  recommended?: boolean;
  kind?: "now" | "roadmap" | "legacy";
  executable?: boolean;
  summary?: string;
  isolation?: "auto" | "worktree" | "apply" | "block" | string;
  execute_workspace?: ExecuteWorkspace;
};

export type PlanActionsResponse = {
  recommended: PlanActionItem | null;
  now?: PlanActionItem[];
  roadmap: PlanActionItem[];
  actions: PlanActionItem[];
};

export type PlanExecutionMergeRecord = {
  status?: "pending" | "merged" | "conflict" | null;
  strategy?: string | null;
  commit_sha?: string | null;
  conflict_files?: string[];
  attempted_at?: string | null;
  completed_at?: string | null;
};

export type PlanExecutionOracleRecord = {
  verdict?: "pass" | "fail" | "skipped" | string;
  detail?: string;
  verify_criterion?: string;
  checked_paths?: string[];
  checked_at?: string;
};

export type PlanExecutionVerifyAfterMergeRecord = {
  status?: "passed" | "failed" | "skipped" | string;
  verify_retries?: number;
  source?: string;
  checked_at?: string;
  oracle?: PlanExecutionOracleRecord;
};

export type PlanExecutionRecord = {
  id: string;
  schema_version?: number;
  action_id?: string;
  action_index?: number;
  action_kind?: "now" | "roadmap" | "legacy";
  action_key?: string;
  action_what?: string;
  action_where?: string;
  action_verify?: string;
  executor?: string;
  executor_label?: string;
  status?: string;
  isolation_requested?: string;
  isolation_effective?: string;
  isolation_override?: string | null;
  git_root?: string;
  base_branch?: string;
  base_sha?: string;
  exec_branch?: string;
  exec_commit_sha?: string | null;
  worktree_path?: string | null;
  merge?: PlanExecutionMergeRecord;
  oracle?: PlanExecutionOracleRecord;
  verify_after_merge?: PlanExecutionVerifyAfterMergeRecord;
  verify_history?: Record<string, unknown>[];
  verify_retries?: number;
  repair_history?: Record<string, unknown>[];
  last_repair?: Record<string, unknown>;
  revise_requested?: boolean;
  revise_note?: string;
  revise_chunk_ref?: string | null;
  revision_of?: string;
  revision_attempt?: number;
  revision_history?: Record<string, unknown>[];
  last_revision?: Record<string, unknown>;
  superseded_by?: string;
  adversarial_note?: string;
  adversarial_source?: string;
  snapshot_id?: string;
  workspace_root?: string;
  workspace_label?: string;
  snapshotted_paths?: string[];
  expected_paths?: string[];
  verification_paths?: string[];
  monitored_paths?: string[];
  verification_artifacts?: {
    ok?: boolean;
    pdf_path?: string | null;
    pdf_page_count?: number | null;
    break_report?: Record<string, unknown> | null;
  };
  execute_workspace_info?: {
    label?: string;
    path?: string;
    paths_found?: string[];
    paths_missing?: string[];
  };
  source_touched_paths?: string[];
  artifact_touched_paths?: string[];
  empty_source_diff?: boolean;
  needs_artifact_review?: boolean;
  touched_paths?: string[];
  paths_outside_expected?: string[];
  draft_summary?: string;
  agent_response?: string;
  agent_log?: string[];
  diff_stat?: string;
  diff?: string;
  started_at?: string;
  completed_at?: string | null;
  pre_verify?: PreVerifyRecord;
};

export function fetchPlanActions(
  sessionId: string,
  permissions?: Record<string, unknown>,
) {
  const qs =
    permissions && Object.keys(permissions).length
      ? `?permissions=${encodeURIComponent(JSON.stringify(permissions))}`
      : "";
  return json<PlanActionsResponse>(
    `/api/sessions/${encodeURIComponent(sessionId)}/plan-actions${qs}`,
  );
}

export type PendingPlanRecord = {
  id: string;
  status: string;
  action_key?: string;
  action_index?: number;
  action_kind?: string;
  action_what?: string;
  action_where?: string;
  action_verify?: string;
  snapshot_text?: string;
  plan_hash?: string;
  created_at?: string;
  approved_at?: string | null;
};

export class PlanSnapshotRequiredError extends Error {
  pendingPlan: PendingPlanRecord;

  constructor(pendingPlan: PendingPlanRecord) {
    super("plan_snapshot_required");
    this.name = "PlanSnapshotRequiredError";
    this.pendingPlan = pendingPlan;
  }
}

export class PlanExecuteDryRunError extends Error {
  code: string;
  remediation?: string[];
  executionId?: string;
  objections?: RoomObjection[];

  constructor(detail: Record<string, unknown>) {
    const message = String(
      detail.message ?? detail.code ?? "execute dry-run blocked",
    );
    super(message);
    this.name = "PlanExecuteDryRunError";
    this.code = String(detail.code ?? "execute_blocked");
    this.remediation = Array.isArray(detail.remediation)
      ? (detail.remediation as string[])
      : undefined;
    this.executionId =
      typeof detail.execution_id === "string" ? detail.execution_id : undefined;
    this.objections = Array.isArray(detail.objections)
      ? (detail.objections as RoomObjection[])
      : undefined;
  }
}

function parseApiErrorBody(text: string): Record<string, unknown> | null {
  try {
    const outer = JSON.parse(text) as { detail?: unknown };
    const detail = outer.detail;
    if (detail && typeof detail === "object") {
      return detail as Record<string, unknown>;
    }
    return null;
  } catch {
    return null;
  }
}

export async function runPlanDryRun(
  sessionId: string,
  opts: {
    actionIndex: number;
    actionKind?: string;
    permissions?: Record<string, unknown>;
  },
) {
  const res = await fetch(
    apiUrl(
      `/api/sessions/${encodeURIComponent(sessionId)}/execute/dry-run`,
    ),
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        action_index: opts.actionIndex,
        action_kind: opts.actionKind ?? null,
        permissions: opts.permissions ?? {},
      }),
    },
  );
  const text = await res.text();
  let body: Record<string, unknown> = {};
  try {
    body = text ? (JSON.parse(text) as Record<string, unknown>) : {};
  } catch {
    /* plain */
  }
  if (res.status === 409) {
    const detail =
      (body.detail as Record<string, unknown> | undefined) ??
      parseApiErrorBody(text) ??
      {};
    if (detail.code === "plan_snapshot_required" && detail.pending_plan) {
      throw new PlanSnapshotRequiredError(
        detail.pending_plan as PendingPlanRecord,
      );
    }
    if (detail.code === "pre_execute_blocked") {
      const err = new Error(
        String(detail.message || "pre_execute hook blocked dry-run"),
      ) as Error & { preVerify?: PreVerifyRecord };
      err.preVerify = detail.pre_verify as PreVerifyRecord | undefined;
      throw err;
    }
    throw new PlanExecuteDryRunError(detail);
  }
  if (!res.ok) {
    throw new Error(text || res.statusText);
  }
  return body as { ok: boolean; execution: PlanExecutionRecord };
}

export function approvePendingPlan(sessionId: string, pendingId: string) {
  return json<{
    ok: boolean;
    pending_plan: PendingPlanRecord;
    awaiting_approval: PendingPlanRecord[];
  }>(
    `/api/sessions/${encodeURIComponent(sessionId)}/execute/pending-plans/${encodeURIComponent(pendingId)}/approve`,
    { method: "POST" },
  );
}

export function rejectPendingPlan(sessionId: string, pendingId: string) {
  return json<{
    ok: boolean;
    pending_plan: PendingPlanRecord;
  }>(
    `/api/sessions/${encodeURIComponent(sessionId)}/execute/pending-plans/${encodeURIComponent(pendingId)}/reject`,
    { method: "POST" },
  );
}

export async function revisePendingPlan(
  sessionId: string,
  pendingId: string,
  opts: {
    comment: string;
    chunkRef?: string;
    lineStart?: number;
    lineEnd?: number;
    executor?: "cursor" | "codex";
    permissions?: Record<string, unknown>;
  },
) {
  const body = await postJsonPlanExecute(
    `/api/sessions/${encodeURIComponent(sessionId)}/execute/pending-plans/${encodeURIComponent(pendingId)}/revise`,
    {
      comment: opts.comment,
      chunk_ref: opts.chunkRef ?? null,
      line_start: opts.lineStart ?? null,
      line_end: opts.lineEnd ?? null,
      executor: opts.executor ?? null,
      permissions: opts.permissions ?? {},
    },
  );
  return body as {
    ok: boolean;
    execution: PlanExecutionRecord;
    superseded_execution: PlanExecutionRecord;
    revision: Record<string, unknown>;
  };
}

export function resolvePlanExecution(
  sessionId: string,
  opts: {
    executionId: string;
    vote: "approve" | "reject";
    permissions?: Record<string, unknown>;
  },
) {
  return json<{
    ok: boolean;
    execution: PlanExecutionRecord;
    approval: Record<string, unknown>;
  }>(`/api/sessions/${encodeURIComponent(sessionId)}/execute/resolve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      execution_id: opts.executionId,
      vote: opts.vote,
      permissions: opts.permissions ?? {},
    }),
  });
}

async function postJsonPlanExecute(
  path: string,
  payload: Record<string, unknown>,
) {
  const res = await fetch(apiUrl(path), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const text = await res.text();
  let body: Record<string, unknown> = {};
  try {
    body = text ? (JSON.parse(text) as Record<string, unknown>) : {};
  } catch {
    /* plain */
  }
  if (!res.ok) {
    const detail =
      body.detail && typeof body.detail === "object"
        ? (body.detail as Record<string, unknown>)
        : { code: "plan_execute_failed", message: body.detail || text };
    throw new PlanExecuteDryRunError(detail);
  }
  return body;
}

async function postPlanMergeAction(
  sessionId: string,
  action: "abort" | "confirm",
  executionId: string,
) {
  const body = await postJsonPlanExecute(
    `/api/sessions/${encodeURIComponent(sessionId)}/execute/merge/${action}`,
    { execution_id: executionId },
  );
  return body as {
    ok: boolean;
    execution: PlanExecutionRecord;
    plan_advance?: Record<string, unknown>;
  };
}

export function abortPlanExecutionMerge(sessionId: string, executionId: string) {
  return postPlanMergeAction(sessionId, "abort", executionId);
}

export function confirmPlanExecutionMerge(sessionId: string, executionId: string) {
  return postPlanMergeAction(sessionId, "confirm", executionId);
}

export async function reverifyPlanExecution(
  sessionId: string,
  executionId: string,
  permissions?: Record<string, unknown>,
) {
  const body = await postJsonPlanExecute(
    `/api/sessions/${encodeURIComponent(sessionId)}/execute/reverify`,
    {
      execution_id: executionId,
      permissions: permissions ?? {},
    },
  );
  return body as {
    ok: boolean;
    execution: PlanExecutionRecord;
    verify_after_merge?: PlanExecutionVerifyAfterMergeRecord;
    repair?: Record<string, unknown> | null;
  };
}

export function overridePlanExecutionIsolation(
  sessionId: string,
  opts: {
    executionId: string;
    mode: "snapshot_override";
    confirmation: string;
    permissions?: Record<string, unknown>;
  },
) {
  return postJsonPlanExecute(
    `/api/sessions/${encodeURIComponent(sessionId)}/execute/isolation/override`,
    {
      execution_id: opts.executionId,
      mode: opts.mode,
      confirmation: opts.confirmation,
      permissions: opts.permissions ?? {},
    },
  ) as Promise<{ ok: boolean; execution: PlanExecutionRecord }>;
}

export type HumanInboxOption = {
  id: string;
  label: string;
  description?: string;
};

export type HumanInboxItem = {
  id: string;
  kind: "question" | "build";
  source?: string;
  status: "pending" | "resolved" | "deferred" | "superseded" | "rejected" | "timeout";
  prompt: string;
  summary?: string | null;
  options?: HumanInboxOption[];
  multi_select?: boolean;
  action_ref?: string | null;
  risks?: string[];
  refs?: string[];
  trigger?: string | null;
  plan_revision?: string | null;
  created_at?: string;
  resolved_at?: string | null;
};

export type HumanInboxPayload = {
  ok: boolean;
  session_id: string;
  human_inbox: HumanInboxItem[];
  inbox_pending: boolean;
  pending_count: number;
  pending_questions: number;
  pending_builds: number;
};

export async function fetchSessionInbox(sessionId: string): Promise<HumanInboxPayload> {
  return json<HumanInboxPayload>(
    `/api/sessions/${encodeURIComponent(sessionId)}/inbox`,
  );
}

export async function resolveInboxItem(
  sessionId: string,
  itemId: string,
  body: {
    selected?: string[];
    decision?: "go" | "defer" | "reject";
    note?: string;
    status?: "resolved" | "deferred" | "rejected";
    append_chat?: boolean;
  },
): Promise<HumanInboxPayload & { human_decision?: string; item: HumanInboxItem }> {
  return json(`/api/sessions/${encodeURIComponent(sessionId)}/inbox/${encodeURIComponent(itemId)}/resolve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}
