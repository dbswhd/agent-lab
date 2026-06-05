import { useCallback, useEffect, useMemo, useState } from "react";
import {
  fetchAgentPlugins,
  patchSessionAgentPlugins,
  type AgentPluginRecord,
  type SlashCommandRecord,
} from "../api/client";

type Props = {
  sessionId: string | null;
  commands: SlashCommandRecord[];
  onPrefillSlash: (slash: string) => void;
  disabled?: boolean;
};

const AGENTS = ["claude", "codex", "cursor"] as const;

export function PluginPanel({
  sessionId,
  commands,
  onPrefillSlash,
  disabled,
}: Props) {
  const [tab, setTab] = useState<"plugins" | "commands">("plugins");
  const [plugins, setPlugins] = useState<AgentPluginRecord[]>([]);
  const [allowlist, setAllowlist] = useState<Record<string, string[]>>({});
  const [busy, setBusy] = useState(false);
  const [hint, setHint] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!sessionId) return;
    const res = await fetchAgentPlugins(sessionId);
    setPlugins(res.plugins ?? []);
    setAllowlist(res.allowlist ?? {});
  }, [sessionId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const grouped = useMemo(() => {
    const map: Record<string, AgentPluginRecord[]> = {
      claude: [],
      codex: [],
      cursor: [],
    };
    for (const row of plugins) {
      const agent = row.agent?.toLowerCase();
      if (agent && map[agent]) map[agent].push(row);
    }
    return map;
  }, [plugins]);

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

  const commandGroups = useMemo(() => {
    const groups: Record<string, SlashCommandRecord[]> = {
      built_in: [],
      claude: [],
      codex: [],
      cursor: [],
      external: [],
    };
    for (const cmd of commands) {
      if (cmd.scope === "external" || cmd.kind === "external") {
        groups.external.push(cmd);
      } else if (cmd.agent === "claude") groups.claude.push(cmd);
      else if (cmd.agent === "codex") groups.codex.push(cmd);
      else if (cmd.agent === "cursor") groups.cursor.push(cmd);
      else groups.built_in.push(cmd);
    }
    return groups;
  }, [commands]);

  if (!sessionId) {
    return <p className="plugin-panel__hint">세션을 선택하면 plugin을 관리할 수 있습니다.</p>;
  }

  return (
    <div className="plugin-panel" data-testid="plugin-panel">
      <div className="plugin-panel__tabs" role="tablist">
        <button
          type="button"
          role="tab"
          className={tab === "plugins" ? "is-active" : ""}
          onClick={() => setTab("plugins")}
        >
          Plugins
        </button>
        <button
          type="button"
          role="tab"
          className={tab === "commands" ? "is-active" : ""}
          onClick={() => setTab("commands")}
        >
          Commands
        </button>
      </div>
      {hint ? <p className="plugin-panel__hint">{hint}</p> : null}
      {tab === "plugins" ? (
        <div className="plugin-panel__body">
          {AGENTS.map((agent) => (
            <section key={agent} className="plugin-panel__agent">
              <h4>{agent}</h4>
              {(grouped[agent] ?? []).length === 0 ? (
                <p className="plugin-panel__empty">목록 없음 — 네이티브 앱에서 추가</p>
              ) : (
                <ul className="plugin-panel__list">
                  {(grouped[agent] ?? []).map((row) => {
                    const enabled = (allowlist[agent] ?? []).includes(row.id);
                    return (
                      <li key={row.id} className="plugin-panel__row">
                        <label>
                          <input
                            type="checkbox"
                            className="mac-checkbox"
                            checked={enabled}
                            disabled={busy || disabled}
                            onChange={(e) =>
                              void togglePlugin(agent, row.id, e.target.checked)
                            }
                          />
                          <span className="plugin-panel__name">{row.name}</span>
                        </label>
                        {row.description ? (
                          <p className="plugin-panel__desc">{row.description}</p>
                        ) : null}
                        {row.native_add_hint ? (
                          <p className="plugin-panel__native-hint">{row.native_add_hint}</p>
                        ) : null}
                      </li>
                    );
                  })}
                </ul>
              )}
            </section>
          ))}
        </div>
      ) : (
        <div className="plugin-panel__body">
          {(
            [
              ["built_in", "Built-in"],
              ["claude", "Claude"],
              ["codex", "Codex"],
              ["cursor", "Cursor"],
              ["external", "External"],
            ] as const
          ).map(([key, label]) =>
            commandGroups[key].length ? (
              <section key={key} className="plugin-panel__agent">
                <h4>{label}</h4>
                <ul className="plugin-panel__list">
                  {commandGroups[key].map((cmd) => (
                    <li key={cmd.id}>
                      <button
                        type="button"
                        className="plugin-panel__cmd"
                        disabled={cmd.enabled === false}
                        onClick={() => onPrefillSlash(cmd.slash)}
                      >
                        <span>{cmd.slash}</span>
                        <span>{cmd.description ?? cmd.label}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              </section>
            ) : null,
          )}
        </div>
      )}
    </div>
  );
}
