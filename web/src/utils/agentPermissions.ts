export type AgentPermissions = {
  cursor?: {
    tools?: boolean;
    local_agent_lab?: boolean;
    local_pipeline?: boolean;
  };
  codex?: {
    cli?: boolean;
  };
  claude?: {
    tools?: boolean;
    write?: boolean;
    local_agent_lab?: boolean;
    local_pipeline?: boolean;
  };
};

const STORAGE_KEY = "agent-lab-permissions-default";

/** Default Claude Code access for room turns (read + edit + agent-lab). */
export const CLAUDE_PERMISSION_DEFAULTS: NonNullable<
  AgentPermissions["claude"]
> = {
  tools: true,
  write: true,
  local_agent_lab: true,
  local_pipeline: false,
};

export function loadDefaultPermissions(): AgentPermissions {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const saved = JSON.parse(raw) as AgentPermissions;
      return {
        ...saved,
        claude: { ...CLAUDE_PERMISSION_DEFAULTS, ...saved.claude },
      };
    }
  } catch {
    /* ignore */
  }
  return { claude: { ...CLAUDE_PERMISSION_DEFAULTS } };
}

export function saveDefaultPermissions(p: AgentPermissions): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(p));
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
      needs: ["Claude Code 읽기", "Claude Code 편집", "agent-lab 폴더", "quant-pipeline 폴더"],
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
    codexCli: boolean;
    claudeTools: boolean;
    claudeWrite: boolean;
    claudeAgentLab: boolean;
    claudePipeline: boolean;
  },
): AgentPermissions {
  const p: AgentPermissions = {};
  if (selected.includes("cursor")) {
    p.cursor = {
      tools: form.cursorTools,
      local_agent_lab: form.cursorAgentLab,
      local_pipeline: form.cursorPipeline,
    };
  }
  if (selected.includes("codex") && form.codexCli) {
    p.codex = { cli: true };
  }
  if (selected.includes("claude")) {
    p.claude = {
      ...CLAUDE_PERMISSION_DEFAULTS,
      tools: form.claudeTools,
      write: form.claudeWrite,
      local_agent_lab: form.claudeAgentLab,
      local_pipeline: form.claudePipeline,
    };
  }
  return p;
}
