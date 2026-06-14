import { useCallback, useEffect, useRef, useState } from "react";
import {
  fetchAgentPlugins,
  fetchCommands,
  patchSessionAgentPlugins,
  patchSessionExternalTools,
  type AgentPluginRecord,
  type SlashCommandRecord,
} from "../api/client";
import { SlashCommandGroupList } from "./SlashCommandGroupList";
import { Avatar } from "./Avatar";
import type { AgentRole } from "../utils/transcript";

type Props = {
  sessionId: string | null;
  commands?: SlashCommandRecord[];
  onPrefillSlash?: (slash: string) => void;
  disabled?: boolean;
  /** Work tab: plugins only, no Commands tab */
  compact?: boolean;
};

const AGENTS = ["cursor", "codex", "claude"] as const;

const AGENT_LABELS: Record<(typeof AGENTS)[number], string> = {
  cursor: "Cursor",
  codex: "Codex",
  claude: "Claude",
};

function emptyGrouped(): Record<(typeof AGENTS)[number], AgentPluginRecord[]> {
  return { cursor: [], codex: [], claude: [] };
}

function normalizeGrouped(
  agents: Record<string, AgentPluginRecord[]> | undefined,
): Record<(typeof AGENTS)[number], AgentPluginRecord[]> {
  const map = emptyGrouped();
  for (const agent of AGENTS) {
    const rows = agents?.[agent] ?? [];
    map[agent] = [...rows].sort((a, b) => a.name.localeCompare(b.name));
  }
  return map;
}

function initialOpenAgents(
  grouped: Record<(typeof AGENTS)[number], AgentPluginRecord[]>,
): Record<string, boolean> {
  const firstWithPlugins = AGENTS.find((a) => grouped[a].length > 0);
  if (!firstWithPlugins) {
    return { cursor: true, codex: false, claude: false };
  }
  return Object.fromEntries(AGENTS.map((a) => [a, a === firstWithPlugins]));
}

const EXTERNAL_DISABLED_HINT: Record<string, string> = {
  env_required: "AGENT_LAB_EXTERNAL_TOOLS=1 필요",
  not_in_session_allowlist: "세션 allowlist에 추가하세요",
  stub: "tools.yaml에 command 설정 필요",
};

function ExternalToolsGroup({
  commands,
  allowlist,
  runnerEnabled,
  open,
  onToggle,
  busy,
  disabled,
  onToggleTool,
}: {
  commands: SlashCommandRecord[];
  allowlist: string[];
  runnerEnabled: boolean;
  open: boolean;
  onToggle: () => void;
  busy: boolean;
  disabled?: boolean;
  onToggleTool: (toolId: string, on: boolean) => void;
}) {
  const external = commands.filter(
    (cmd) => cmd.scope === "external" || cmd.kind === "external",
  );
  const enabledCount = external.filter((row) =>
    allowlist.includes(row.id),
  ).length;

  return (
    <section className="plugin-agent-group">
      <button
        type="button"
        className="plugin-agent-group__head"
        aria-expanded={open}
        onClick={onToggle}
      >
        <span className="plugin-agent-group__chevron" aria-hidden>
          {open ? "▾" : "▸"}
        </span>
        <span className="plugin-agent-group__name">External</span>
        <span className="plugin-agent-group__counts">
          <span className="badge">{external.length}</span>
          {enabledCount > 0 ? (
            <span className="badge badge--ok">{enabledCount} on</span>
          ) : null}
        </span>
      </button>
      {open ? (
        !runnerEnabled ? (
          <p className="plugin-panel__hint">
            외부 runner 비활성 — 서버에 <code>AGENT_LAB_EXTERNAL_TOOLS=1</code>{" "}
            설정 후 ~/.agent-lab/tools.yaml 을 등록하세요.
          </p>
        ) : external.length === 0 ? (
          <p className="plugin-panel__empty">등록된 외부 명령 없음</p>
        ) : (
          <ul className="plugin-panel__list">
            {external.map((row) => {
              const enabled = allowlist.includes(row.id);
              const rowDisabled =
                busy || disabled || row.status === "stub" || !runnerEnabled;
              return (
                <li key={row.id} className="plugin-panel__row">
                  <label className="plugin-panel__label">
                    <input
                      type="checkbox"
                      className="checkbox"
                      checked={enabled}
                      disabled={rowDisabled}
                      onChange={(e) => onToggleTool(row.id, e.target.checked)}
                    />
                    <span className="plugin-panel__name">
                      <code>{row.slash}</code> — {row.label}
                    </span>
                  </label>
                  {row.description ? (
                    <p className="plugin-panel__desc">{row.description}</p>
                  ) : null}
                  {row.enabled === false && row.disabled_reason ? (
                    <p className="plugin-panel__native-hint">
                      {EXTERNAL_DISABLED_HINT[row.disabled_reason] ??
                        row.disabled_reason}
                    </p>
                  ) : null}
                </li>
              );
            })}
          </ul>
        )
      ) : null}
    </section>
  );
}

function AgentPluginGroup({
  agent,
  plugins,
  allowlist,
  open,
  onToggle,
  busy,
  disabled,
  onTogglePlugin,
}: {
  agent: (typeof AGENTS)[number];
  plugins: AgentPluginRecord[];
  allowlist: string[];
  open: boolean;
  onToggle: () => void;
  busy: boolean;
  disabled?: boolean;
  onTogglePlugin: (pluginId: string, on: boolean) => void;
}) {
  const enabledCount = plugins.filter((row) =>
    allowlist.includes(row.id),
  ).length;

  return (
    <section className="plugin-agent-group">
      <button
        type="button"
        className="plugin-agent-group__head"
        aria-expanded={open}
        onClick={onToggle}
      >
        <span className="plugin-agent-group__chevron" aria-hidden>
          {open ? "▾" : "▸"}
        </span>
        <Avatar role={agent as AgentRole} size={20} />
        <span className="plugin-agent-group__name">{AGENT_LABELS[agent]}</span>
        <span className="plugin-agent-group__counts">
          <span className="badge">{plugins.length}</span>
          {enabledCount > 0 ? (
            <span className="badge badge--ok">{enabledCount} on</span>
          ) : null}
        </span>
      </button>
      {open ? (
        plugins.length === 0 ? (
          <p className="plugin-panel__empty">
            목록 없음 — 네이티브 앱에서 추가
          </p>
        ) : (
          <ul className="plugin-panel__list">
            {plugins.map((row) => {
              const enabled = allowlist.includes(row.id);
              return (
                <li key={row.id} className="plugin-panel__row">
                  <label className="plugin-panel__label">
                    <input
                      type="checkbox"
                      className="checkbox"
                      checked={enabled}
                      disabled={busy || disabled}
                      onChange={(e) => onTogglePlugin(row.id, e.target.checked)}
                    />
                    <span className="plugin-panel__name">{row.name}</span>
                  </label>
                  {row.description ? (
                    <p className="plugin-panel__desc">{row.description}</p>
                  ) : null}
                  {row.native_add_hint ? (
                    <p className="plugin-panel__native-hint">
                      {row.native_add_hint}
                    </p>
                  ) : null}
                </li>
              );
            })}
          </ul>
        )
      ) : null}
      {agent === "cursor" && open ? (
        <p
          className="plugin-panel__cursor-ide-hint"
          data-testid="cursor-ide-mcp-hint"
        >
          Cursor MCP/plugins are inherited from Cursor IDE (Settings → Features
          → MCP). The bridge has no list API — activity stream may show MCP tool
          names during runs.
        </p>
      ) : null}
    </section>
  );
}

export function PluginPanel({
  sessionId,
  commands = [],
  onPrefillSlash,
  disabled,
  compact = false,
}: Props) {
  const [tab, setTab] = useState<"plugins" | "commands">("plugins");
  const [grouped, setGrouped] =
    useState<Record<(typeof AGENTS)[number], AgentPluginRecord[]>>(
      emptyGrouped,
    );
  const [allowlist, setAllowlist] = useState<Record<string, string[]>>({});
  const [busy, setBusy] = useState(false);
  const [hint, setHint] = useState<string | null>(null);
  const [openAgents, setOpenAgents] = useState<Record<string, boolean>>({});
  const [externalAllowlist, setExternalAllowlist] = useState<string[]>([]);
  const [externalRunnerEnabled, setExternalRunnerEnabled] = useState(false);
  const [externalOpen, setExternalOpen] = useState(false);
  const [catalogCommands, setCatalogCommands] =
    useState<SlashCommandRecord[]>(commands);
  const accordionInitRef = useRef<string | null>(null);

  const refresh = useCallback(async () => {
    if (!sessionId) return;
    const [res, cmdRes] = await Promise.all([
      fetchAgentPlugins(sessionId),
      fetchCommands(sessionId),
    ]);
    const nextGrouped = normalizeGrouped(res.agents);
    setGrouped(nextGrouped);
    setAllowlist(res.allowlist ?? {});
    setCatalogCommands(cmdRes.commands ?? []);
    setExternalAllowlist(cmdRes.external_tools?.allowlist ?? []);
    setExternalRunnerEnabled(Boolean(cmdRes.external_tools?.enabled));

    if (accordionInitRef.current !== sessionId) {
      accordionInitRef.current = sessionId;
      setOpenAgents(initialOpenAgents(nextGrouped));
      setExternalOpen(
        (cmdRes.commands ?? []).some((c) => c.kind === "external"),
      );
    }
  }, [sessionId]);

  useEffect(() => {
    if (!sessionId) {
      accordionInitRef.current = null;
      setGrouped(emptyGrouped());
      setAllowlist({});
      setOpenAgents({});
      setExternalAllowlist([]);
      setExternalRunnerEnabled(false);
      setCatalogCommands([]);
      setHint(null);
      return;
    }
    accordionInitRef.current = null;
    void refresh();
  }, [sessionId, refresh]);

  async function toggleExternalTool(toolId: string, on: boolean) {
    if (!sessionId || disabled) return;
    setBusy(true);
    setHint(null);
    try {
      const current = new Set(externalAllowlist);
      if (on) current.add(toolId);
      else current.delete(toolId);
      const res = await patchSessionExternalTools(sessionId, [...current]);
      setExternalAllowlist(res.external_tools?.allowlist ?? res.enabled ?? []);
      setHint("저장됨");
    } catch (e) {
      setHint(e instanceof Error ? e.message : "저장 실패");
    } finally {
      setBusy(false);
    }
  }

  async function togglePlugin(agent: string, pluginId: string, on: boolean) {
    if (!sessionId || disabled) return;
    setBusy(true);
    setHint(null);
    try {
      const current = new Set(allowlist[agent] ?? []);
      if (on) current.add(pluginId);
      else current.delete(pluginId);
      const res = await patchSessionAgentPlugins(sessionId, {
        agent,
        enabled: [...current],
      });
      setAllowlist(res.allowlist ?? {});
      setHint("저장됨");
    } catch (e) {
      setHint(e instanceof Error ? e.message : "저장 실패");
    } finally {
      setBusy(false);
    }
  }

  const resolvedCommands =
    catalogCommands.length > 0 ? catalogCommands : commands;

  if (!sessionId) {
    return (
      <p className="plugin-panel__hint">
        세션을 선택하면 plugin을 관리할 수 있습니다.
      </p>
    );
  }

  const pluginBody = (
    <div className="plugin-panel__body">
      {AGENTS.map((agent) => (
        <AgentPluginGroup
          key={agent}
          agent={agent}
          plugins={grouped[agent]}
          allowlist={allowlist[agent] ?? []}
          open={Boolean(openAgents[agent])}
          onToggle={() =>
            setOpenAgents((prev) => ({ ...prev, [agent]: !prev[agent] }))
          }
          busy={busy}
          disabled={disabled}
          onTogglePlugin={(pluginId, on) =>
            void togglePlugin(agent, pluginId, on)
          }
        />
      ))}
      <ExternalToolsGroup
        commands={resolvedCommands}
        allowlist={externalAllowlist}
        runnerEnabled={externalRunnerEnabled}
        open={externalOpen}
        onToggle={() => setExternalOpen((v) => !v)}
        busy={busy}
        disabled={disabled}
        onToggleTool={(toolId, on) => void toggleExternalTool(toolId, on)}
      />
    </div>
  );

  if (compact) {
    return (
      <div
        className="plugin-panel plugin-panel--compact"
        data-testid="work-plugin-panel"
      >
        {hint ? <p className="plugin-panel__hint">{hint}</p> : null}
        {pluginBody}
      </div>
    );
  }

  return (
    <div className="plugin-panel" data-testid="plugin-panel">
      <div className="plugin-panel__tabs turn-seg" role="tablist">
        <button
          type="button"
          role="tab"
          aria-selected={tab === "plugins"}
          className={tab === "plugins" ? "is-active" : ""}
          onClick={() => setTab("plugins")}
        >
          Plugins
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === "commands"}
          className={tab === "commands" ? "is-active" : ""}
          onClick={() => setTab("commands")}
        >
          Commands
        </button>
      </div>
      {hint ? <p className="plugin-panel__hint">{hint}</p> : null}
      {tab === "plugins" ? (
        pluginBody
      ) : (
        <div className="plugin-panel__body">
          <SlashCommandGroupList
            commands={resolvedCommands}
            variant="panel"
            onPrefillSlash={onPrefillSlash}
            maxPerAgentGroup={48}
            emptyHint="등록된 slash 명령이 없습니다."
          />
        </div>
      )}
    </div>
  );
}
