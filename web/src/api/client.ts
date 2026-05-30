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
};

export type ChatLine = {
  role: string;
  agent?: string | null;
  content: string;
  ts?: string;
  /** Parallel wave within one human message (1 = first replies, 2+ = peer discussion). */
  parallel_round?: number;
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
};

export function apiBase(): string {
  const fromEnv = import.meta.env.VITE_API_BASE as string | undefined;
  if (fromEnv) return fromEnv.replace(/\/$/, "");
  const w = window as Window & { __TAURI_INTERNALS__?: unknown };
  if (w.__TAURI_INTERNALS__) return "http://127.0.0.1:8765";
  // Vite dev (browser on :1420 tauri dev or :5173 web dev)
  if (import.meta.env.DEV && typeof window !== "undefined") {
    const port = window.location.port;
    if (port === "1420" || port === "5173") {
      return "http://127.0.0.1:8765";
    }
  }
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

export function fetchHealth() {
  return json<{ ok: boolean; provider?: string; model?: string }>("/api/health");
}

export function fetchAgents() {
  return json<{ agents: AgentOption[]; default: string[] }>("/api/agents");
}

export function fetchBackends() {
  return json<{ default: string | null; options: BackendOption[] }>(
    "/api/backends",
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

async function consumeSse(
  res: Response,
  onEvent: (data: Record<string, unknown>) => void,
): Promise<void> {
  const reader = res.body?.getReader();
  if (!reader) throw new Error("no response body");
  const dec = new TextDecoder();
  let buf = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    const parts = buf.split("\n\n");
    buf = parts.pop() ?? "";
    for (const part of parts) {
      for (const line of part.split("\n")) {
        if (line.startsWith("data: ")) {
          onEvent(JSON.parse(line.slice(6)) as Record<string, unknown>);
        }
      }
    }
  }
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
  /** Composer turn profile id (quick/discuss/review/free). */
  turnProfile?: string;
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
  form.append("turn_profile", opts?.turnProfile ?? "discuss");
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
  if (!res.ok) throw new Error(await res.text());
  await consumeSse(res, onEvent);
}

export async function cancelRoomRun(): Promise<void> {
  const res = await fetch(apiUrl("/api/room/runs/cancel"), { method: "POST" });
  if (!res.ok) throw new Error(await res.text());
}

export function fetchTurnProfileRecommendation() {
  return json<{
    recommended: string;
    default: string;
    scores: Record<string, number>;
    stats: Record<string, { up: number; down: number; total: number }>;
    total_feedback: number;
  }>("/api/room/turn-profile-recommendation");
}

export function submitTurnFeedback(opts: {
  sessionId: string;
  vote: "up" | "down";
  turnIndex?: number;
  profile?: string;
}) {
  return json<{
    ok: boolean;
    feedback: { vote: string; profile: string; ts: string };
    recommendation: Awaited<ReturnType<typeof fetchTurnProfileRecommendation>>;
  }>("/api/room/turn-feedback", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      session_id: opts.sessionId,
      vote: opts.vote,
      turn_index: opts.turnIndex ?? -1,
      profile: opts.profile,
    }),
  });
}
