import { useCallback, useEffect, useRef, useState } from "react";
import type { AgentOption, MissionTemplateSummary } from "../api/client";
import { fetchMissionTemplates, fetchSessionSetupOptions } from "../api/client";
import { Avatar } from "./Avatar";
import type {
  SessionSetupOptions,
  WorkspacePreset,
} from "../utils/sessionSetup";
import {
  CUSTOM_WORKSPACE_ID,
  getStoredWorkspaceId,
  getStoredWorkspacePath,
  setStoredSessionTemplate,
  setStoredWorkspaceId,
  setStoredWorkspacePath,
  type SessionTemplate,
  type TradingMissionPreset,
} from "../utils/sessionSetup";
import { pickWorkspaceFolder } from "../utils/pickWorkspaceFolder";
import type { AgentRole } from "../utils/transcript";

export type NewSessionAgentChoice = {
  id: string;
  thread: "new" | string;
};

export type NewSessionParams = {
  workspaceId: string;
  workspacePath: string | null;
  sessionTemplate: string;
  /** Mission OS template from sessions/_templates (Gate 2-B). */
  missionTemplateId?: string | null;
  topic?: string | null;
  agents: NewSessionAgentChoice[];
};

type Props = {
  open: boolean;
  agents: AgentOption[];
  initialTopic?: string | null;
  onClose: () => void;
  onCreate: (params: NewSessionParams) => void;
};

const TEAM_AGENT_ORDER = ["cursor", "codex", "claude"] as const;
type TeamAgentId = (typeof TEAM_AGENT_ORDER)[number];

type AgentPick = { on: boolean; thread: "new" | string };

function missionTemplateLabel(tpl: MissionTemplateSummary): string {
  const title =
    typeof tpl.meta?.title === "string" ? tpl.meta.title.trim() : "";
  return title || tpl.id;
}

function defaultAgentPicks(
  agents: AgentOption[],
): Record<TeamAgentId, AgentPick> {
  const ready = new Set(agents.filter((a) => a.ready).map((a) => a.id));
  const use = ready.size ? ready : new Set(agents.map((a) => a.id));
  return {
    cursor: { on: use.has("cursor"), thread: "new" },
    codex: { on: use.has("codex"), thread: "new" },
    claude: { on: use.has("claude"), thread: "new" },
  };
}

/** New Session modal — prototype app/newsession.jsx layout + real API wiring. */
export function NewSessionDialog({
  open,
  agents,
  initialTopic = null,
  onClose,
  onCreate,
}: Props) {
  const [setupOptions, setSetupOptions] = useState<SessionSetupOptions | null>(
    null,
  );
  const [loadError, setLoadError] = useState(false);

  const [workspaceId, setWorkspaceId] = useState(() => getStoredWorkspaceId());
  const [workspacePath, setWorkspacePath] = useState<string | null>(() =>
    getStoredWorkspacePath(),
  );
  const [agentPicks, setAgentPicks] = useState<Record<TeamAgentId, AgentPick>>(
    () => defaultAgentPicks(agents),
  );
  const [sessionTemplate, setSessionTemplate] = useState("general");
  const [missionTemplates, setMissionTemplates] = useState<
    MissionTemplateSummary[]
  >([]);
  const [missionTemplateId, setMissionTemplateId] = useState("");
  const [presetTopic, setPresetTopic] = useState<string | null>(null);

  const dirRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;
    setLoadError(false);
    setAgentPicks(defaultAgentPicks(agents));
    setMissionTemplateId("");
    setPresetTopic(initialTopic?.trim() || null);
    void Promise.all([fetchSessionSetupOptions(), fetchMissionTemplates()])
      .then(([opts, mission]) => {
        setSetupOptions(opts);
        setMissionTemplates(mission.templates ?? []);
        setWorkspaceId((prev) => prev || opts.defaults.workspace_id);
        setSessionTemplate(opts.defaults.session_template || "general");
      })
      .catch(() => setLoadError(true));
  }, [open, agents, initialTopic]);

  const applyMissionTemplate = useCallback(
    (templateId: string) => {
      setMissionTemplateId(templateId);
      if (!templateId) return;
      const tpl = missionTemplates.find((row) => row.id === templateId);
      if (tpl?.topic?.trim() && !presetTopic) {
        setPresetTopic(tpl.topic.trim());
      }
    },
    [missionTemplates, presetTopic],
  );

  const applyTradingPreset = useCallback((preset: TradingMissionPreset) => {
    setWorkspaceId(preset.workspace_id);
    setWorkspacePath(null);
    setStoredWorkspaceId(preset.workspace_id);
    setStoredWorkspacePath(null);
    setSessionTemplate(preset.session_template);
    setStoredSessionTemplate(preset.session_template);
    setPresetTopic(preset.topic ?? null);
  }, []);

  const toggleAgent = useCallback((id: TeamAgentId) => {
    setAgentPicks((prev) => ({
      ...prev,
      [id]: { ...prev[id], on: !prev[id].on },
    }));
  }, []);

  const setAgentThread = useCallback(
    (id: TeamAgentId, thread: "new" | string) => {
      setAgentPicks((prev) => ({
        ...prev,
        [id]: { on: true, thread },
      }));
    },
    [],
  );

  useEffect(() => {
    if (!open) return;
    const id = window.requestAnimationFrame(() => dirRef.current?.focus());
    return () => window.cancelAnimationFrame(id);
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  const pickWorkspace = useCallback((preset: WorkspacePreset) => {
    setWorkspaceId(preset.id);
    setWorkspacePath(null);
    setStoredWorkspaceId(preset.id);
    setStoredWorkspacePath(null);
  }, []);

  const browseFolder = useCallback(async () => {
    setWorkspaceId(CUSTOM_WORKSPACE_ID);
    setStoredWorkspaceId(CUSTOM_WORKSPACE_ID);
    const activePreset = setupOptions?.workspaces.find(
      (w) => w.id === workspaceId,
    );
    const defaultPath =
      workspacePath ??
      activePreset?.path ??
      setupOptions?.workspaces.find((w) => w.available)?.path ??
      null;
    const picked = await pickWorkspaceFolder(defaultPath);
    if (picked) {
      setWorkspacePath(picked);
      setStoredWorkspacePath(picked);
    }
  }, [workspacePath, workspaceId, setupOptions]);

  const isCustom = workspaceId === CUSTOM_WORKSPACE_ID;
  const preset =
    setupOptions?.workspaces.find((w) => w.id === workspaceId) ?? null;
  const displayDir = isCustom ? (workspacePath ?? "") : (preset?.path ?? "");
  const displayBranch =
    (preset as (WorkspacePreset & { branch?: string }) | null)?.branch ?? null;

  const orderedAgents = TEAM_AGENT_ORDER.map((id) =>
    agents.find((a) => a.id === id),
  ).filter(Boolean) as AgentOption[];

  const agentThreads = setupOptions?.agent_threads ?? {};
  const chosen = orderedAgents.filter(
    (a) => agentPicks[a.id as TeamAgentId]?.on,
  );
  const canCreate =
    (isCustom ? Boolean(workspacePath?.trim()) : Boolean(displayDir)) &&
    chosen.length > 0;

  function submit() {
    if (!canCreate) return;
    const wid = workspaceId;
    const wpath = isCustom ? workspacePath : null;
    setStoredWorkspaceId(wid);
    setStoredWorkspacePath(wpath);
    onCreate({
      workspaceId: wid,
      workspacePath: wpath,
      sessionTemplate,
      missionTemplateId: missionTemplateId.trim() || null,
      topic: presetTopic,
      agents: chosen.map((a) => {
        const role = a.id as TeamAgentId;
        return {
          id: a.id,
          thread: agentPicks[role]?.thread ?? "new",
        };
      }),
    });
  }

  if (!open) return null;

  const workspaces = setupOptions?.workspaces ?? [];
  const templates = (setupOptions?.session_templates ??
    []) as SessionTemplate[];
  const tradingPreset = setupOptions?.trading_mission_preset ?? null;

  return (
    <div className="ns-overlay" role="presentation" onMouseDown={onClose}>
      <div
        className="ns-modal"
        role="dialog"
        aria-modal="true"
        aria-label="새 Session"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <header className="ns-modal__head">
          <div className="ns-modal__heading">
            <span className="ns-modal__icon" aria-hidden="true">
              <svg
                width="16"
                height="16"
                viewBox="0 0 16 16"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.75"
                strokeLinecap="round"
              >
                <path d="M8 3v10M3 8h10" />
              </svg>
            </span>
            <div>
              <h2 className="ns-modal__title">새 Session</h2>
              <p className="ns-modal__sub">워크스페이스와 팀을 선택하세요</p>
            </div>
          </div>
          <button
            type="button"
            className="icon-btn"
            onClick={onClose}
            aria-label="닫기"
          >
            <svg
              width="16"
              height="16"
              viewBox="0 0 16 16"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.75"
              strokeLinecap="round"
            >
              <path d="M3 3l10 10M13 3L3 13" />
            </svg>
          </button>
        </header>

        <div className="ns-modal__body scroll-y">
          <section className="ns-block">
            <div className="ns-block__head">
              <span className="ns-block__label">작업 폴더</span>
              <span className="ns-block__hint">
                이 세션의 모든 에이전트가 사용할 루트 폴더
              </span>
            </div>

            <div className="ns-dir">
              <span className="ns-dir__icon" aria-hidden="true">
                <svg
                  width="17"
                  height="17"
                  viewBox="0 0 16 16"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.6"
                  strokeLinecap="round"
                >
                  <path d="M1 4a1 1 0 0 1 1-1h4l2 2h6a1 1 0 0 1 1 1v7a1 1 0 0 1-1 1H2a1 1 0 0 1-1-1V4z" />
                </svg>
              </span>
              <input
                ref={dirRef}
                className="ns-dir__input"
                value={isCustom ? (workspacePath ?? "") : displayDir}
                readOnly={!isCustom}
                spellCheck={false}
                placeholder="~/path/to/project"
                onChange={(e) => {
                  if (!isCustom) return;
                  setWorkspacePath(e.target.value || null);
                }}
              />
              {displayBranch && !isCustom ? (
                <span className="ns-dir__branch">
                  <svg
                    width="13"
                    height="13"
                    viewBox="0 0 16 16"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="1.6"
                    strokeLinecap="round"
                    aria-hidden="true"
                  >
                    <circle cx="5" cy="4" r="1.5" />
                    <circle cx="5" cy="12" r="1.5" />
                    <circle cx="11" cy="4" r="1.5" />
                    <path d="M5 5.5v5M5 5.5C5 8 11 8 11 5.5" />
                  </svg>
                  {displayBranch}
                </span>
              ) : null}
              <button
                type="button"
                className="btn btn--sm"
                onClick={() => void browseFolder()}
              >
                <svg
                  width="14"
                  height="14"
                  viewBox="0 0 16 16"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.6"
                  strokeLinecap="round"
                  aria-hidden
                >
                  <path d="M1 4a1 1 0 0 1 1-1h4l2 2h6a1 1 0 0 1 1 1v7a1 1 0 0 1-1 1H2a1 1 0 0 1-1-1V4z" />
                </svg>
                찾아보기
              </button>
            </div>

            {workspaces.length > 0 ? (
              <div className="ns-recent">
                <span className="ns-recent__label">최근</span>
                <div className="ns-recent__list">
                  {workspaces.map((w) => {
                    const active = w.id === workspaceId && !isCustom;
                    const branch = (w as WorkspacePreset & { branch?: string })
                      .branch;
                    return (
                      <button
                        key={w.id}
                        type="button"
                        className={`ns-recent__item${active ? " is-active" : ""}${!w.available ? " ns-recent__item--unavailable" : ""}`}
                        disabled={!w.available}
                        onClick={() => pickWorkspace(w)}
                      >
                        <svg
                          width="15"
                          height="15"
                          viewBox="0 0 16 16"
                          fill="none"
                          stroke="currentColor"
                          strokeWidth="1.6"
                          strokeLinecap="round"
                          aria-hidden="true"
                        >
                          <path d="M1 4a1 1 0 0 1 1-1h4l2 2h6a1 1 0 0 1 1 1v7a1 1 0 0 1-1 1H2a1 1 0 0 1-1-1V4z" />
                        </svg>
                        <span className="ns-recent__path">
                          {w.path ?? w.label}
                        </span>
                        {branch ? (
                          <span className="ns-recent__branch">
                            <svg
                              width="11"
                              height="11"
                              viewBox="0 0 16 16"
                              fill="none"
                              stroke="currentColor"
                              strokeWidth="1.6"
                              strokeLinecap="round"
                              aria-hidden
                            >
                              <circle cx="5" cy="4" r="1.5" />
                              <circle cx="5" cy="12" r="1.5" />
                              <circle cx="11" cy="4" r="1.5" />
                              <path d="M5 5.5v5M5 5.5C5 8 11 8 11 5.5" />
                            </svg>
                            {branch}
                          </span>
                        ) : null}
                        <span className="ns-recent__time">{w.label}</span>
                        {active ? (
                          <span
                            className="ns-recent__check"
                            aria-label="selected"
                          >
                            <svg
                              width="14"
                              height="14"
                              viewBox="0 0 16 16"
                              fill="none"
                              stroke="currentColor"
                              strokeWidth="2"
                              strokeLinecap="round"
                            >
                              <path d="M2 8l4 4 8-8" />
                            </svg>
                          </span>
                        ) : null}
                      </button>
                    );
                  })}
                  <button
                    type="button"
                    className={`ns-recent__item${isCustom ? " is-active" : ""}`}
                    onClick={() => void browseFolder()}
                  >
                    <svg
                      width="15"
                      height="15"
                      viewBox="0 0 16 16"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="1.6"
                      strokeLinecap="round"
                      aria-hidden="true"
                    >
                      <path d="M8 3v10M3 8h10" />
                    </svg>
                    <span className="ns-recent__path">다른 폴더…</span>
                  </button>
                </div>
              </div>
            ) : null}

            {loadError ? (
              <p className="ns-block__hint" style={{ color: "var(--warn)" }}>
                설정 로드 실패 — API 연결을 확인하세요.
              </p>
            ) : null}
          </section>

          {missionTemplates.length > 0 ? (
            <section className="ns-block">
              <div className="ns-block__head">
                <span className="ns-block__label">Mission 템플릿</span>
                <span className="ns-block__hint">
                  sessions/_templates · plan.md 사전 복사 (Gate 2-B)
                </span>
              </div>
              <select
                className="mac-popup session-setup-bar__select"
                value={missionTemplateId}
                onChange={(e) => applyMissionTemplate(e.target.value)}
                aria-label="Mission 템플릿"
              >
                <option value="">— 선택 안 함 —</option>
                {missionTemplates.map((tpl) => (
                  <option key={tpl.id} value={tpl.id}>
                    {missionTemplateLabel(tpl)}
                    {tpl.hash_match ? " ✓" : ""}
                  </option>
                ))}
              </select>
              {missionTemplateId ? (
                <p className="ns-block__hint" style={{ marginTop: 8 }}>
                  {missionTemplates.find((row) => row.id === missionTemplateId)
                    ?.hash_match
                    ? "Pre-approved — 첫 전송 후 plan fast-path (APPROVED)."
                    : "Hash drift — 전체 plan workflow (CLARIFY부터)."}
                  {missionTemplates.find((row) => row.id === missionTemplateId)
                    ?.topic
                    ? " Topic이 composer에 채워집니다."
                    : null}
                </p>
              ) : null}
            </section>
          ) : null}

          {templates.length > 0 ? (
            <section className="ns-block">
              <div className="ns-block__head">
                <span className="ns-block__label">세션 템플릿</span>
                <span className="ns-block__hint">
                  Room 가이던스·예산 프리셋
                </span>
              </div>
              <select
                className="mac-popup session-setup-bar__select"
                value={sessionTemplate}
                onChange={(e) => {
                  const next = e.target.value;
                  setSessionTemplate(next);
                  setStoredSessionTemplate(next);
                  if (next !== "trading-mission") {
                    setPresetTopic(null);
                  }
                }}
                aria-label="세션 템플릿"
              >
                {templates.map((tpl) => (
                  <option key={tpl.id} value={tpl.id}>
                    {tpl.label}
                  </option>
                ))}
              </select>
              {tradingPreset ? (
                <button
                  type="button"
                  className="btn btn--sm"
                  style={{ marginTop: 8 }}
                  onClick={() => applyTradingPreset(tradingPreset)}
                >
                  Trading Mission (장전) 원클릭
                </button>
              ) : null}
              {presetTopic ? (
                <p className="ns-block__hint" style={{ marginTop: 8 }}>
                  장전 topic이 준비됩니다 — Session 생성 후 전송하세요.
                </p>
              ) : null}
            </section>
          ) : null}

          {presetTopic ? (
            <section className="ns-block ns-block--sample">
              <div className="ns-block__head">
                <span className="ns-block__label">샘플 주제</span>
                <span className="ns-block__hint">
                  Session 생성 후 composer에 입력됩니다
                </span>
              </div>
              <p className="ns-sample-topic">{presetTopic}</p>
            </section>
          ) : null}

          <section className="ns-block">
            <div className="ns-block__head">
              <span className="ns-block__label">팀</span>
              <span className="ns-block__hint">이 세션에 참여할 에이전트</span>
            </div>
            <div className="ns-agents">
              {orderedAgents.map((ag) => {
                const role = ag.id as TeamAgentId;
                const pick = agentPicks[role] ?? {
                  on: false,
                  thread: "new" as const,
                };
                const threads = agentThreads[role] ?? [];
                const resumed =
                  pick.thread !== "new"
                    ? threads.find((th) => th.id === pick.thread)
                    : null;
                return (
                  <div
                    key={ag.id}
                    className={`ns-agent${pick.on ? "" : " is-off"}`}
                  >
                    <label className="ns-agent__pick">
                      <input
                        type="checkbox"
                        className="checkbox"
                        checked={pick.on}
                        onChange={() => toggleAgent(role)}
                        aria-label={`${ag.label} 포함`}
                      />
                    </label>
                    <Avatar role={role} label={ag.label} size={28} />
                    <div className="ns-agent__id">
                      <span className="ns-agent__name">{ag.label}</span>
                      {ag.model ? (
                        <span className="ns-agent__model">{ag.model}</span>
                      ) : null}
                    </div>
                    <div className="ns-agent__thread">
                      <div className="ns-select">
                        {pick.thread === "new" ? <PlusIcon /> : <ResumeIcon />}
                        <select
                          value={pick.thread}
                          disabled={!pick.on}
                          aria-label={`${ag.label} 세션`}
                          onChange={(e) =>
                            setAgentThread(
                              role,
                              e.target.value === "new" ? "new" : e.target.value,
                            )
                          }
                        >
                          <option value="new">새 스레드</option>
                          {threads.map((th) => (
                            <option key={th.id} value={th.id}>
                              이어하기 · {th.label}
                            </option>
                          ))}
                        </select>
                        <ChevronDownIcon />
                      </div>
                      {resumed ? (
                        <span className="ns-agent__meta">
                          {resumed.msgs}개 메시지 · 마지막 {resumed.last}
                        </span>
                      ) : null}
                    </div>
                    {!ag.ready ? (
                      <span className="badge badge--warn">not ready</span>
                    ) : null}
                  </div>
                );
              })}
            </div>
          </section>
        </div>

        <footer className="ns-modal__foot">
          <span className="ns-foot__summary">
            {chosen.length > 0 ? (
              chosen.map((a) => (
                <Avatar
                  key={a.id}
                  role={a.id as AgentRole}
                  label={a.label}
                  size={20}
                />
              ))
            ) : (
              <span className="ns-foot__warn">
                <svg
                  width="13"
                  height="13"
                  viewBox="0 0 16 16"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.75"
                  strokeLinecap="round"
                  aria-hidden="true"
                >
                  <path d="M8 3v5M8 11v1" />
                  <path d="M8 1 1 14h14L8 1z" />
                </svg>
                에이전트를 1명 이상 선택하세요
              </span>
            )}
          </span>
          <div className="ns-foot__actions">
            <button type="button" className="btn" onClick={onClose}>
              취소
            </button>
            <button
              type="button"
              className="btn btn--primary"
              disabled={!canCreate}
              onClick={submit}
            >
              <svg
                width="15"
                height="15"
                viewBox="0 0 16 16"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                aria-hidden="true"
              >
                <path d="M2 8l4 4 8-8" />
              </svg>
              {presetTopic ? "샘플 준비하기" : "Session 만들기"}
            </button>
          </div>
        </footer>
      </div>
    </div>
  );
}

function PlusIcon() {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      aria-hidden
    >
      <path d="M8 3v10M3 8h10" />
    </svg>
  );
}

function ResumeIcon() {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      aria-hidden
    >
      <path d="M4 4v8h8M12 8 4 4" />
    </svg>
  );
}

function ChevronDownIcon() {
  return (
    <svg
      width="13"
      height="13"
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      aria-hidden
    >
      <path d="M4 6l4 4 4-4" />
    </svg>
  );
}
