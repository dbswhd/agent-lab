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
import { Avatar } from "./Avatar";
import type { AgentRole } from "../utils/transcript";

type Props = {
  capabilities: AgentCapabilitiesMap;
  onChange: (caps: AgentCapabilitiesMap) => void;
  resolvedCwd?: Record<string, string>;
  selectedAgents?: string[];
  disabled?: boolean;
  compact?: boolean;
  hideToggle?: boolean;
  embedded?: boolean;
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
  hideToggle = false,
  embedded = false,
  onSave,
  saveBusy,
  saveHint,
}: Props) {
  const [open, setOpen] = useState(false);
  const showBody = hideToggle || open;
  const activeSet = new Set(
    (selectedAgents?.length ? selectedAgents : AGENT_ORDER).map((a) =>
      a.toLowerCase(),
    ),
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
        "agent-settings",
        compact ? "agent-settings--compact" : undefined,
        embedded ? "agent-settings--embedded" : undefined,
      ]
        .filter(Boolean)
        .join(" ")}
      data-settings-embedded={embedded || undefined}
    >
      {!hideToggle ? (
        <button
          type="button"
          className="settings-expand-btn"
          onClick={() => setOpen((v) => !v)}
          aria-expanded={open}
        >
          {open ? "▾" : "▸"} 에이전트별 세션 설정
          <span className="settings-expand-btn__hint">작업 폴더 · 도구</span>
        </button>
      ) : null}

      {showBody ? (
        <>
          <div className="agent-settings__toolbar">
            <button
              type="button"
              className="btn btn--sm"
              disabled={disabled}
              onClick={() =>
                onChange(cloneCapabilities(DEFAULT_AGENT_CAPABILITIES))
              }
            >
              기본값
            </button>
            <button
              type="button"
              className="btn btn--sm"
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
                className="btn btn--sm btn--primary"
                disabled={disabled || saveBusy}
                onClick={() => void onSave()}
              >
                {saveBusy ? "저장 중…" : "세션에 저장"}
              </button>
            ) : null}
          </div>
          {saveHint && !hideToggle ? (
            <p className="settings-save-hint">{saveHint}</p>
          ) : null}

          <div className="agent-settings__grid">
            {AGENT_ORDER.map((agent) => {
              const cap = capabilities[agent];
              const dimmed = selectedAgents?.length && !activeSet.has(agent);
              const resolved = resolvedCwd?.[agent];
              return (
                <fieldset
                  key={agent}
                  className={[
                    "agent-settings__card",
                    dimmed ? "agent-settings__card--dim" : undefined,
                  ]
                    .filter(Boolean)
                    .join(" ")}
                  disabled={disabled}
                >
                  <legend className="agent-settings__legend">
                    <Avatar role={agent as AgentRole} size={20} />
                    {agentLabel(agent)}
                    {cap.label ? (
                      <span className="agent-settings__model">{cap.label}</span>
                    ) : null}
                  </legend>

                  <label className="agent-settings__field">
                    <span>작업 폴더 역할</span>
                    <select
                      className="ns-select"
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

                  <label className="agent-settings__field">
                    <span>직접 경로</span>
                    <div className="ns-dir" style={{ height: 32 }}>
                      <input
                        className="ns-dir__input"
                        readOnly
                        placeholder="경로 (선택)"
                        value={cap.cwd_path ?? ""}
                        title={cap.cwd_path ?? ""}
                      />
                      <button
                        type="button"
                        className="btn btn--sm"
                        onClick={() => void browseCwd(agent)}
                      >
                        폴더…
                      </button>
                      {cap.cwd_path ? (
                        <button
                          type="button"
                          className="icon-btn"
                          aria-label="경로 지우기"
                          onClick={() =>
                            patch((c) => setAgentCwdPath(c, agent, undefined))
                          }
                        >
                          ×
                        </button>
                      ) : null}
                    </div>
                  </label>

                  {resolved ? (
                    <p className="agent-settings__resolved" title={resolved}>
                      적용 cwd:{" "}
                      {resolved.length > 48
                        ? `…${resolved.slice(-44)}`
                        : resolved}
                    </p>
                  ) : null}

                  <div className="agent-settings__tools">
                    <span className="agent-settings__tools-label">도구</span>
                    {TOOL_OPTIONS[agent].map((t) => (
                      <label key={t.id} className="agent-settings__tool">
                        <input
                          type="checkbox"
                          className="checkbox"
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
        </>
      ) : null}
    </div>
  );
}
