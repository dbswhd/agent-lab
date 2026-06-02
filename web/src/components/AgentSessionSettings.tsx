import { useState } from "react";
import {
  agentLabel,
  cloneCapabilities,
  CWD_ROLE_OPTIONS,
  DEFAULT_AGENT_CAPABILITIES,
  SPECIALIST_AGENT_CAPABILITIES,
  TOOL_OPTIONS,
  toggleTool,
  setAgentCwdPath,
  setAgentCwdRole,
  type AgentCapabilitiesMap,
  type AgentId,
} from "../utils/agentCapabilities";
import { pickWorkspaceFolder } from "../utils/pickWorkspaceFolder";

type Props = {
  capabilities: AgentCapabilitiesMap;
  onChange: (caps: AgentCapabilitiesMap) => void;
  resolvedCwd?: Record<string, string>;
  selectedAgents?: string[];
  disabled?: boolean;
  compact?: boolean;
  onSave?: () => void | Promise<void>;
  saveBusy?: boolean;
  saveHint?: string | null;
};

const AGENT_ORDER: AgentId[] = ["cursor", "codex", "claude"];

export function AgentSessionSettings({
  capabilities,
  onChange,
  resolvedCwd,
  selectedAgents,
  disabled,
  compact = false,
  onSave,
  saveBusy,
  saveHint,
}: Props) {
  const [open, setOpen] = useState(false);
  const activeSet = new Set(
    (selectedAgents?.length ? selectedAgents : AGENT_ORDER).map((a) => a.toLowerCase()),
  );

  function patch(updater: (c: AgentCapabilitiesMap) => AgentCapabilitiesMap) {
    onChange(updater(cloneCapabilities(capabilities)));
  }

  async function browseCwd(agent: AgentId) {
    const picked = await pickWorkspaceFolder(capabilities[agent].cwd_path);
    if (!picked) return;
    onChange(setAgentCwdPath(capabilities, agent, picked));
  }

  return (
    <div
      className={[
        "agent-session-settings",
        compact ? "agent-session-settings--compact" : undefined,
      ]
        .filter(Boolean)
        .join(" ")}
    >
      <button
        type="button"
        className="agent-session-settings__toggle"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        <span className="agent-session-settings__toggle-label">에이전트별 세션</span>
        <span className="agent-session-settings__toggle-hint">
          작업 폴더 · 도구
        </span>
      </button>

      {open ? (
        <div className="agent-session-settings__body">
          <div className="agent-session-settings__toolbar">
            <button
              type="button"
              className="mac-btn-secondary agent-session-settings__preset"
              disabled={disabled}
              onClick={() =>
                onChange(cloneCapabilities(DEFAULT_AGENT_CAPABILITIES))
              }
            >
              기본값
            </button>
            <button
              type="button"
              className="mac-btn-secondary agent-session-settings__preset"
              disabled={disabled}
              onClick={() =>
                onChange(cloneCapabilities(SPECIALIST_AGENT_CAPABILITIES))
              }
            >
              분업 프리셋
            </button>
            {onSave ? (
              <button
                type="button"
                className="mac-btn-primary agent-session-settings__save"
                disabled={disabled || saveBusy}
                onClick={() => void onSave()}
              >
                {saveBusy ? "저장 중…" : "세션에 저장"}
              </button>
            ) : null}
          </div>
          {saveHint ? (
            <p className="agent-session-settings__save-hint">{saveHint}</p>
          ) : null}

          <div className="agent-session-settings__grid">
            {AGENT_ORDER.map((agent) => {
              const cap = capabilities[agent];
              const dimmed = selectedAgents?.length && !activeSet.has(agent);
              const resolved = resolvedCwd?.[agent];
              return (
                <fieldset
                  key={agent}
                  className={[
                    "agent-session-settings__card",
                    dimmed ? "agent-session-settings__card--dim" : undefined,
                  ]
                    .filter(Boolean)
                    .join(" ")}
                  disabled={disabled}
                >
                  <legend>{agentLabel(agent)}</legend>
                  {cap.label ? (
                    <p className="agent-session-settings__role">{cap.label}</p>
                  ) : null}

                  <label className="agent-session-settings__field">
                    <span>작업 폴더 역할</span>
                    <select
                      className="mac-popup"
                      value={cap.cwd_path ? "custom" : cap.cwd_role}
                      onChange={(e) => {
                        const v = e.target.value;
                        if (v === "custom") return;
                        patch((c) => setAgentCwdRole(c, agent, v));
                      }}
                    >
                      {CWD_ROLE_OPTIONS.map((o) => (
                        <option key={o.id} value={o.id}>
                          {o.label}
                        </option>
                      ))}
                      <option value="custom">직접 지정…</option>
                    </select>
                  </label>

                  <div className="agent-session-settings__path-row">
                    <input
                      type="text"
                      className="mac-textfield agent-session-settings__path"
                      readOnly
                      placeholder="폴더 경로 (선택)"
                      value={cap.cwd_path ?? ""}
                      title={cap.cwd_path ?? ""}
                    />
                    <button
                      type="button"
                      className="mac-btn-secondary"
                      onClick={() => void browseCwd(agent)}
                    >
                      폴더…
                    </button>
                    {cap.cwd_path ? (
                      <button
                        type="button"
                        className="mac-btn-secondary"
                        onClick={() => patch((c) => setAgentCwdPath(c, agent, undefined))}
                      >
                        지우기
                      </button>
                    ) : null}
                  </div>

                  {resolved ? (
                    <p className="agent-session-settings__resolved" title={resolved}>
                      적용 cwd: {resolved.length > 48 ? `…${resolved.slice(-44)}` : resolved}
                    </p>
                  ) : null}

                  <div className="agent-session-settings__tools">
                    <span className="agent-session-settings__tools-label">도구</span>
                    {TOOL_OPTIONS[agent].map((t) => (
                      <label key={t.id} className="agent-session-settings__tool">
                        <input
                          type="checkbox"
                          className="mac-checkbox"
                          checked={cap.tools.includes(t.id)}
                          onChange={() =>
                            patch((c) => toggleTool(c, agent, t.id))
                          }
                        />
                        {t.label}
                      </label>
                    ))}
                  </div>
                </fieldset>
              );
            })}
          </div>
        </div>
      ) : null}
    </div>
  );
}
