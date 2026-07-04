import { apiJson as json, apiUrl } from "./http";

// ── Workspace Files (Files tab) ──
export type WorkspaceFileRoot = {
  root_id: string;
  label: string;
  kind: "session" | "workspace";
  is_primary: boolean;
  missing: boolean;
};

export type WorkspaceFileEntry = {
  name: string;
  type: "dir" | "file";
  size: number | null;
  mtime: number;
  git_status?: string;
};

export type WorkspaceFileContent = {
  root_id: string;
  path: string;
  kind: "text" | "binary" | "large";
  size: number;
  content: string | null;
  truncated?: boolean;
};

export function listWorkspaceFileRoots(sessionId: string) {
  return json<{ roots: WorkspaceFileRoot[] }>(
    `/api/sessions/${encodeURIComponent(sessionId)}/files/roots`,
  );
}

export function listWorkspaceFiles(
  sessionId: string,
  rootId: string,
  path = "",
) {
  const params = new URLSearchParams({ root_id: rootId, path });
  return json<{ root_id: string; path: string; entries: WorkspaceFileEntry[] }>(
    `/api/sessions/${encodeURIComponent(sessionId)}/files?${params.toString()}`,
  );
}

export function readWorkspaceFile(
  sessionId: string,
  rootId: string,
  path: string,
) {
  const params = new URLSearchParams({ root_id: rootId, path });
  return json<WorkspaceFileContent>(
    `/api/sessions/${encodeURIComponent(sessionId)}/files/content?${params.toString()}`,
  );
}

export function writeSessionFile(
  sessionId: string,
  rootId: string,
  path: string,
  content: string,
) {
  return json<{ root_id: string; path: string; size: number; ok: boolean }>(
    `/api/sessions/${encodeURIComponent(sessionId)}/files/content`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ root_id: rootId, path, content }),
    },
  );
}

/** Absolute URL for a file's raw bytes — use as <img src> / <iframe src>. */
export function workspaceFileRawUrl(
  sessionId: string,
  rootId: string,
  path: string,
): string {
  const params = new URLSearchParams({ root_id: rootId, path });
  return apiUrl(
    `/api/sessions/${encodeURIComponent(sessionId)}/files/raw?${params.toString()}`,
  );
}

// ── Background Tasks ─────────────────────────────────────────────────────────

export type BgTaskStatus =
  | "queued"
  | "running"
  | "done"
  | "failed"
  | "cancelled";

export type BgTask = {
  task_id: string;
  session_id: string;
  label: string;
  command: string[];
  cwd: string;
  status: BgTaskStatus;
  created_at: string;
  started_at: string | null;
  ended_at: string | null;
  exit_code: number | null;
};

export type BgLogLine = {
  text: string;
  stream?: "out" | "err";
};

export function submitBgTask(
  sessionId: string,
  label: string,
  command: string[],
  cwd?: string,
): Promise<BgTask> {
  return json<BgTask>(
    `/api/sessions/${encodeURIComponent(sessionId)}/bg-tasks`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ label, command, cwd: cwd ?? null }),
    },
  );
}

export function listBgTasks(sessionId: string): Promise<{ tasks: BgTask[] }> {
  return json<{ tasks: BgTask[] }>(
    `/api/sessions/${encodeURIComponent(sessionId)}/bg-tasks`,
  );
}

export function getBgTaskLog(
  sessionId: string,
  taskId: string,
  offset = 0,
): Promise<{ task_id: string; offset: number; lines: BgLogLine[] }> {
  return json(
    `/api/sessions/${encodeURIComponent(sessionId)}/bg-tasks/${encodeURIComponent(taskId)}/log?offset=${offset}`,
  );
}

export async function cancelBgTask(
  sessionId: string,
  taskId: string,
): Promise<void> {
  await fetch(
    apiUrl(
      `/api/sessions/${encodeURIComponent(sessionId)}/bg-tasks/${encodeURIComponent(taskId)}`,
    ),
    { method: "DELETE" },
  );
}

// ─────────────────────────────────────────────────────────────────────────────

// ── Dev Preview ──────────────────────────────────────────────────────────────

export type PreviewStatus = {
  port: number | null;
  alive: boolean;
};

export function getPreviewStatus(sessionId: string): Promise<PreviewStatus> {
  return json<PreviewStatus>(
    `/api/sessions/${encodeURIComponent(sessionId)}/preview/status`,
  );
}

export function setPreviewPort(
  sessionId: string,
  port: number,
): Promise<PreviewStatus> {
  return json<PreviewStatus>(
    `/api/sessions/${encodeURIComponent(sessionId)}/preview/port`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ port }),
    },
  );
}

export async function clearPreviewPort(sessionId: string): Promise<void> {
  await fetch(
    apiUrl(`/api/sessions/${encodeURIComponent(sessionId)}/preview/port`),
    { method: "DELETE" },
  );
}

export type PreviewProbeResult = PreviewStatus & {
  probed: number[];
};

export function probePreviewPort(
  sessionId: string,
): Promise<PreviewProbeResult> {
  return json<PreviewProbeResult>(
    `/api/sessions/${encodeURIComponent(sessionId)}/preview/probe`,
    { method: "POST" },
  );
}

export type DevServerPreset = {
  id: string;
  label: string;
  command: string[];
  cwd: string;
};

export function getPreviewPresets(
  sessionId: string,
): Promise<{ presets: DevServerPreset[] }> {
  return json<{ presets: DevServerPreset[] }>(
    `/api/sessions/${encodeURIComponent(sessionId)}/preview/presets`,
  );
}

// ─────────────────────────────────────────────────────────────────────────────

export type WisdomHit = {
  id?: string;
  source?: string;
  title?: string;
  score?: number;
  snippet?: string;
  at?: string;
  path?: string;
  session_id?: string;
};

export type WisdomIndexStatus = {
  enabled: boolean;
  document_count: number;
  built_at?: string | null;
  path?: string;
  cross_session?: boolean;
  auto_enabled?: boolean;
};

export type WisdomSearchPayload = {
  enabled: boolean;
  query: string;
  hits: WisdomHit[];
  hit_count: number;
  cross_session_hits?: WisdomHit[];
  cross_session_hit_count?: number;
  index?: WisdomIndexStatus;
};

export function fetchSessionWisdomSearch(
  sessionId: string,
  q: string,
  limit = 20,
  crossSession = false,
) {
  const params = new URLSearchParams({
    q,
    limit: String(limit),
    cross_session: crossSession ? "true" : "false",
  });
  return json<{ ok: boolean; session_id: string } & WisdomSearchPayload>(
    `/api/sessions/${encodeURIComponent(sessionId)}/wisdom-search?${params}`,
  );
}

export function rebuildSessionWisdomIndex(sessionId: string) {
  return json<{ ok: boolean; session_id: string; index: WisdomIndexStatus }>(
    `/api/sessions/${encodeURIComponent(sessionId)}/wisdom-index/rebuild`,
    { method: "POST" },
  );
}
