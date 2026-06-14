export type WorkspacePreset = {
  id: string;
  label: string;
  path: string | null;
  available: boolean;
};

export type AgentThreadOption = {
  id: string;
  label: string;
  msgs: number;
  last: string;
};

export type SessionTemplate = {
  id: string;
  label: string;
  description: string;
  default_phase?: string | null;
};

export type TradingMissionPreset = {
  workspace_id: string;
  session_template: string;
  turn_profile?: string;
  topic?: string;
  session_goal?: string;
};

export type SessionSetupDefaults = {
  workspace_id: string;
  session_template: string;
};

export type SessionSetupOptions = {
  workspaces: WorkspacePreset[];
  agent_threads?: Partial<
    Record<"cursor" | "codex" | "claude", AgentThreadOption[]>
  >;
  session_templates?: SessionTemplate[];
  trading_mission_preset?: TradingMissionPreset | null;
  defaults: SessionSetupDefaults;
};

export const CUSTOM_WORKSPACE_ID = "custom";

const WORKSPACE_KEY = "agent-lab-workspace-id";
const WORKSPACE_PATH_KEY = "agent-lab-workspace-path";
const SESSION_TEMPLATE_KEY = "agent-lab-session-template";

export function getStoredWorkspaceId(fallback = "agent-lab"): string {
  try {
    const v = localStorage.getItem(WORKSPACE_KEY);
    return v?.trim() || fallback;
  } catch {
    return fallback;
  }
}

export function getStoredWorkspacePath(): string | null {
  try {
    const v = localStorage.getItem(WORKSPACE_PATH_KEY);
    return v?.trim() || null;
  } catch {
    return null;
  }
}

export function setStoredWorkspaceId(id: string): void {
  localStorage.setItem(WORKSPACE_KEY, id);
}

export function setStoredWorkspacePath(path: string | null): void {
  if (path?.trim()) {
    localStorage.setItem(WORKSPACE_PATH_KEY, path.trim());
  } else {
    localStorage.removeItem(WORKSPACE_PATH_KEY);
  }
}

export function getStoredSessionTemplate(fallback = "general"): string {
  try {
    const v = localStorage.getItem(SESSION_TEMPLATE_KEY);
    return v?.trim() || fallback;
  } catch {
    return fallback;
  }
}

export function setStoredSessionTemplate(id: string): void {
  localStorage.setItem(SESSION_TEMPLATE_KEY, id);
}

export function workspaceLabelFromId(
  workspaces: WorkspacePreset[],
  id: string | undefined,
): string {
  if (!id) return "";
  if (id === CUSTOM_WORKSPACE_ID) return "선택한 폴더";
  return workspaces.find((w) => w.id === id)?.label ?? id;
}

export function sessionSetupSummary(
  meta: Record<string, unknown> | undefined,
  run: Record<string, unknown> | undefined,
): string | null {
  const label =
    (meta?.workspace_label as string | undefined) ||
    ((run?.workspace_binding as { label?: string } | undefined)?.label ?? "");
  const bindingPath = (run?.workspace_binding as { path?: string } | undefined)
    ?.path;
  if (!label && !bindingPath) return null;
  if (label) return label;
  return bindingPath ?? null;
}
