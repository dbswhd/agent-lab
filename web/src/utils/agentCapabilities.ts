export type AgentId = "cursor" | "codex" | "claude";

export type AgentCapability = {
  tools: string[];
  cwd_role: string;
  label?: string;
  restrictions?: string[];
  cwd_path?: string;
};

export type AgentCapabilitiesMap = Record<AgentId, AgentCapability>;

export const DEFAULT_AGENT_CAPABILITIES: AgentCapabilitiesMap = {
  cursor: {
    tools: ["sdk_edit"],
    cwd_role: "primary",
    label: "execute · SDK patch",
  },
  codex: {
    tools: ["codex_cli"],
    cwd_role: "repo",
    label: "decompose · verify · sandbox",
  },
  claude: {
    tools: ["read_only"],
    cwd_role: "review",
    label: "risk · read-only review",
  },
};

/** @deprecated UI removed — regression fixture only; use route-driven capability seed. */
export const SPECIALIST_AGENT_CAPABILITIES: AgentCapabilitiesMap = {
  cursor: {
    tools: ["sdk_edit"],
    cwd_role: "execute",
    label: "R2 patch · SDK",
    restrictions: ["R2 only — apply Codex/Claude R1 findings"],
  },
  codex: {
    tools: ["codex_cli", "sandbox"],
    cwd_role: "repo",
    label: "R1 decompose · verify",
    restrictions: ["no unilateral execute without plan"],
  },
  claude: {
    tools: ["read_only"],
    cwd_role: "review",
    label: "R1 risk · counter-evidence",
    restrictions: ["no file writes"],
  },
};

export const CWD_ROLE_OPTIONS: { id: string; label: string }[] = [
  { id: "primary", label: "주 작업 폴더 (세션)" },
  { id: "execute", label: "실행 폴더 (세션 바인딩)" },
  { id: "repo", label: "quant-pipeline" },
  { id: "review", label: "프로젝트 루트 (읽기)" },
];

export const TOOL_OPTIONS: Record<AgentId, { id: string; label: string }[]> = {
  cursor: [{ id: "sdk_edit", label: "SDK 패치" }],
  codex: [
    { id: "codex_cli", label: "Codex CLI" },
    { id: "sandbox", label: "Sandbox" },
  ],
  claude: [{ id: "read_only", label: "읽기 전용" }],
};

const AGENTS: AgentId[] = ["cursor", "codex", "claude"];

function normalizeOne(
  raw: unknown,
  fallback: AgentCapability,
): AgentCapability {
  const r =
    raw && typeof raw === "object" ? (raw as Record<string, unknown>) : {};
  const toolsRaw = r.tools;
  const tools = Array.isArray(toolsRaw)
    ? toolsRaw.map((t) => String(t).trim()).filter(Boolean)
    : [...fallback.tools];
  const restrictionsRaw = r.restrictions;
  const restrictions = Array.isArray(restrictionsRaw)
    ? restrictionsRaw
        .map((x) => String(x).trim())
        .filter(Boolean)
        .slice(0, 6)
    : fallback.restrictions;
  const out: AgentCapability = {
    tools: tools.length ? tools : [...fallback.tools],
    cwd_role:
      String(r.cwd_role || fallback.cwd_role).trim() || fallback.cwd_role,
    label:
      String(r.label || fallback.label || "").slice(0, 120) || fallback.label,
  };
  if (restrictions?.length) out.restrictions = restrictions;
  const cwdPath = String(r.cwd_path || "").trim();
  if (cwdPath) out.cwd_path = cwdPath.slice(0, 500);
  return out;
}

export function parseAgentCapabilities(raw: unknown): AgentCapabilitiesMap {
  const src =
    raw && typeof raw === "object" ? (raw as Record<string, unknown>) : {};
  return {
    cursor: normalizeOne(src.cursor, DEFAULT_AGENT_CAPABILITIES.cursor),
    codex: normalizeOne(src.codex, DEFAULT_AGENT_CAPABILITIES.codex),
    claude: normalizeOne(src.claude, DEFAULT_AGENT_CAPABILITIES.claude),
  };
}

export function cloneCapabilities(
  caps: AgentCapabilitiesMap,
): AgentCapabilitiesMap {
  return {
    cursor: { ...caps.cursor, tools: [...caps.cursor.tools] },
    codex: { ...caps.codex, tools: [...caps.codex.tools] },
    claude: { ...caps.claude, tools: [...caps.claude.tools] },
  };
}

export function capabilitiesForApi(
  caps: AgentCapabilitiesMap,
): Record<string, AgentCapability> {
  const out: Record<string, AgentCapability> = {};
  for (const id of AGENTS) {
    const c = caps[id];
    const row: AgentCapability = {
      tools: [...c.tools],
      cwd_role: c.cwd_role,
    };
    if (c.label?.trim()) row.label = c.label.trim();
    if (c.cwd_path?.trim()) row.cwd_path = c.cwd_path.trim();
    if (c.restrictions?.length) row.restrictions = [...c.restrictions];
    out[id] = row;
  }
  return out;
}

export function agentLabel(id: AgentId): string {
  if (id === "cursor") return "Cursor";
  if (id === "codex") return "Codex";
  return "Claude";
}

export function toggleTool(
  caps: AgentCapabilitiesMap,
  agent: AgentId,
  toolId: string,
): AgentCapabilitiesMap {
  const next = cloneCapabilities(caps);
  const set = new Set(next[agent].tools);
  if (set.has(toolId)) set.delete(toolId);
  else set.add(toolId);
  next[agent] = { ...next[agent], tools: [...set] };
  return next;
}

export function setAgentCwdRole(
  caps: AgentCapabilitiesMap,
  agent: AgentId,
  cwd_role: string,
): AgentCapabilitiesMap {
  const next = cloneCapabilities(caps);
  next[agent] = { ...next[agent], cwd_role };
  if (cwd_role !== "custom") {
    const { cwd_path: _drop, ...rest } = next[agent];
    next[agent] = rest as AgentCapability;
  }
  return next;
}

export function setAgentCwdPath(
  caps: AgentCapabilitiesMap,
  agent: AgentId,
  cwd_path: string | undefined,
): AgentCapabilitiesMap {
  const next = cloneCapabilities(caps);
  if (cwd_path?.trim()) {
    next[agent] = {
      ...next[agent],
      cwd_path: cwd_path.trim(),
      cwd_role: "primary",
    };
  } else {
    const { cwd_path: _drop, ...rest } = next[agent];
    next[agent] = rest as AgentCapability;
  }
  return next;
}
