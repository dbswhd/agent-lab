export type BackendOption = { id: string; label: string; ready: boolean };

export type AgentOption = { id: string; label: string; ready: boolean };

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
  form.append("agent_rounds", String(opts?.agentRounds ?? 2));
  form.append("review_mode", String(opts?.reviewMode ?? false));
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
  });
  if (!res.ok) throw new Error(await res.text());
  await consumeSse(res, onEvent);
}
