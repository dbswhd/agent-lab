export type AgentPermissions = {
  cursor?: {
    tools?: boolean;
    local_agent_lab?: boolean;
    local_pipeline?: boolean;
    local_lecture_script?: boolean;
  };
  codex?: {
    cli?: boolean;
  };
  claude?: {
    tools?: boolean;
    write?: boolean;
    local_agent_lab?: boolean;
    local_pipeline?: boolean;
    local_lecture_script?: boolean;
  };
};

const STORAGE_KEY = "agent-lab-permissions-default";

/** Maximum access for room debate + execute (all roots, all tools). */
export const FULL_AGENT_PERMISSIONS: Required<
  Pick<AgentPermissions, "cursor" | "codex" | "claude">
> = {
  cursor: {
    tools: true,
    local_agent_lab: true,
    local_pipeline: true,
    local_lecture_script: true,
  },
  codex: { cli: true },
  claude: {
    tools: true,
    write: true,
    local_agent_lab: true,
    local_pipeline: true,
    local_lecture_script: true,
  },
};

/** @deprecated alias — use FULL_AGENT_PERMISSIONS */
export const CURSOR_PERMISSION_DEFAULTS = FULL_AGENT_PERMISSIONS.cursor;
export const CLAUDE_PERMISSION_DEFAULTS = FULL_AGENT_PERMISSIONS.claude;
export const CODEX_PERMISSION_DEFAULTS = FULL_AGENT_PERMISSIONS.codex;

export function fullAgentPermissions(): AgentPermissions {
  return {
    cursor: { ...FULL_AGENT_PERMISSIONS.cursor },
    codex: { ...FULL_AGENT_PERMISSIONS.codex },
    claude: { ...FULL_AGENT_PERMISSIONS.claude },
  };
}

/** Full permissions for agents selected this turn (room default). */
export function roomPermissions(selected: string[]): AgentPermissions {
  const full = fullAgentPermissions();
  const p: AgentPermissions = {};
  if (selected.includes("cursor")) p.cursor = { ...full.cursor };
  if (selected.includes("codex")) p.codex = { ...full.codex };
  if (selected.includes("claude")) p.claude = { ...full.claude };
  return p;
}

export function loadDefaultPermissions(): AgentPermissions {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return fullAgentPermissions();
    const parsed = JSON.parse(raw) as AgentPermissions;
    return {
      cursor: { ...FULL_AGENT_PERMISSIONS.cursor, ...parsed.cursor },
      codex: { ...FULL_AGENT_PERMISSIONS.codex, ...parsed.codex },
      claude: { ...FULL_AGENT_PERMISSIONS.claude, ...parsed.claude },
    };
  } catch {
    return fullAgentPermissions();
  }
}

export function saveDefaultPermissions(p: AgentPermissions): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(p));
}

export function clearSavedPermissionDefaults(): void {
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch {
    /* ignore */
  }
}

export function hasSavedPermissionDefaults(): boolean {
  try {
    return localStorage.getItem(STORAGE_KEY) !== null;
  } catch {
    return false;
  }
}

/** Agents that may need elevated access this turn */
export function agentsNeedingPermissionPrompt(
  selected: string[],
): { id: string; label: string; needs: string[] }[] {
  const out: { id: string; label: string; needs: string[] }[] = [];
  if (selected.includes("cursor")) {
    out.push({
      id: "cursor",
      label: "Cursor",
      needs: ["도구(파일 읽기/검색)", "agent-lab 폴더", "quant-pipeline 폴더"],
    });
  }
  if (selected.includes("codex")) {
    out.push({
      id: "codex",
      label: "Codex",
      needs: ["Codex CLI 실행"],
    });
  }
  if (selected.includes("claude")) {
    out.push({
      id: "claude",
      label: "Claude",
      needs: [
        "Claude Code 읽기",
        "Claude Code 편집",
        "agent-lab 폴더",
        "quant-pipeline 폴더",
      ],
    });
  }
  return out;
}

export function buildPermissionsFromForm(
  selected: string[],
  form: {
    cursorTools: boolean;
    cursorAgentLab: boolean;
    cursorPipeline: boolean;
    cursorLectureScript: boolean;
    codexCli: boolean;
    claudeTools: boolean;
    claudeWrite: boolean;
    claudeAgentLab: boolean;
    claudePipeline: boolean;
    claudeLectureScript: boolean;
  },
): AgentPermissions {
  const p: AgentPermissions = {};
  if (selected.includes("cursor")) {
    p.cursor = {
      ...FULL_AGENT_PERMISSIONS.cursor,
      tools: form.cursorTools,
      local_agent_lab: form.cursorAgentLab,
      local_pipeline: form.cursorPipeline,
      local_lecture_script: form.cursorLectureScript,
    };
  }
  if (selected.includes("codex")) {
    p.codex = { cli: form.codexCli };
  }
  if (selected.includes("claude")) {
    p.claude = {
      ...CLAUDE_PERMISSION_DEFAULTS,
      tools: form.claudeTools,
      write: form.claudeWrite,
      local_agent_lab: form.claudeAgentLab,
      local_pipeline: form.claudePipeline,
      local_lecture_script: form.claudeLectureScript,
    };
  }
  return p;
}
