import { useCallback, useEffect, useState } from "react";
import type { SessionDetail } from "../api/client";
import {
  fetchCommands,
  fetchSessionAgentCapabilities,
  patchSessionAgentCapabilities,
  type AgentHealthRow,
  type SlashCommandRecord,
} from "../api/client";
import { AgentCredentialsPanel } from "./AgentCredentialsPanel";
import { AgentSessionSettings } from "./AgentSessionSettings";
import { ApiDiagnosticsBar } from "./ApiDiagnosticsBar";
import { ContextPreviewPanel } from "./ContextPreviewPanel";
import { PluginPanel } from "./PluginPanel";
import { SlashCommandGroupList } from "./SlashCommandGroupList";
import { ThemeToggle } from "./ThemeToggle";
import { Avatar } from "./Avatar";
import { SettingsSectionIcon } from "./SettingsSectionIcon";
import { useTweaksDemo } from "../context/TweaksDemoContext";
import { useLocale } from "../i18n/useLocale";
import { localeLabel } from "../i18n/locale";
import {
  clearSavedPermissionDefaults,
  hasSavedPermissionDefaults,
} from "../utils/agentPermissions";
import {
  capabilitiesForApi,
  cloneCapabilities,
  DEFAULT_AGENT_CAPABILITIES,
  parseAgentCapabilities,
  type AgentCapabilitiesMap,
} from "../utils/agentCapabilities";
import type { ComposerTurnProfile } from "../utils/turnProfile";
import { roomPermissions } from "../utils/agentPermissions";
import type { AgentRole } from "../utils/transcript";

type Props = {
  sessionId: string | null;
  session: SessionDetail | null;
  selectedAgents: string[];
  turnProfile: ComposerTurnProfile;
  efficiencyOn: boolean;
  onBack: () => void;
  apiOk?: boolean;
  healthAgents?: AgentHealthRow[];
  healthLoading?: boolean;
  reconnecting?: boolean;
  sessionsDir?: string | null;
  probeBridgeFailed?: boolean;
  onRefreshDiagnostics?: () => void;
  onReconnectCursor?: () => void;
  onOpenLegacy?: () => void;
};

function TweaksSettingsActions({ onBack }: { onBack: () => void }) {
  const tweaks = useTweaksDemo();

  return (
    <button
      type="button"
      className="btn"
      onClick={() => {
        onBack();
        tweaks.setPanelOpen(true);
      }}
    >
      Tweaks 열기
    </button>
  );
}

export function SettingsPage({
  sessionId,
  session,
  selectedAgents,
  turnProfile,
  efficiencyOn,
  onBack,
  apiOk = true,
  healthAgents = [],
  healthLoading,
  reconnecting,
  sessionsDir = null,
  probeBridgeFailed = false,
  onRefreshDiagnostics,
  onReconnectCursor,
  onOpenLegacy,
}: Props) {
  const { locale, setLocale, t } = useLocale();
  const [capabilities, setCapabilities] = useState<AgentCapabilitiesMap>(
    () => cloneCapabilities(DEFAULT_AGENT_CAPABILITIES),
  );
  const [resolvedCwd, setResolvedCwd] = useState<Record<string, string>>({});
  const [saveBusy, setSaveBusy] = useState(false);
  const [saveHint, setSaveHint] = useState<string | null>(null);
  const [commands, setCommands] = useState<SlashCommandRecord[]>([]);
  const [copiedSlash, setCopiedSlash] = useState<string | null>(null);
  const [agentSettingsOpen, setAgentSettingsOpen] = useState(false);
  const [permissionDefaultsSaved, setPermissionDefaultsSaved] = useState(
    hasSavedPermissionDefaults,
  );

  useEffect(() => {
    setPermissionDefaultsSaved(hasSavedPermissionDefaults());
  }, []);

  const loadCapabilities = useCallback(async () => {
    if (!sessionId) return;
    const raw = session?.run?.agent_capabilities;
    if (raw && typeof raw === "object") {
      setCapabilities(parseAgentCapabilities(raw));
    }
    try {
      const res = await fetchSessionAgentCapabilities(
        sessionId,
        roomPermissions(selectedAgents) as Record<string, unknown>,
      );
      if (!raw && res.agent_capabilities) {
        setCapabilities(parseAgentCapabilities(res.agent_capabilities));
      }
      setResolvedCwd(res.resolved_cwd ?? {});
    } catch {
      /* ignore */
    }
  }, [sessionId, session?.run?.agent_capabilities, selectedAgents]);

  useEffect(() => {
    void loadCapabilities();
  }, [loadCapabilities]);

  useEffect(() => {
    let cancelled = false;
    void fetchCommands(sessionId)
      .then((res) => {
        if (!cancelled) setCommands(res.commands ?? []);
      })
      .catch(() => {
        if (!cancelled) setCommands([]);
      });
    return () => {
      cancelled = true;
    };
  }, [sessionId]);

  const saveCapabilities = async () => {
    if (!sessionId) return;
    setSaveBusy(true);
    setSaveHint(null);
    try {
      const res = await patchSessionAgentCapabilities(
        sessionId,
        capabilitiesForApi(capabilities),
      );
      setResolvedCwd(res.resolved_cwd ?? {});
      setSaveHint("저장됨 ✓");
    } catch (e) {
      setSaveHint(e instanceof Error ? e.message : "저장 실패");
    } finally {
      setSaveBusy(false);
    }
  };

  const copySlash = async (slash: string) => {
    try {
      await navigator.clipboard.writeText(slash);
    } catch {
      /* ignore */
    }
    setCopiedSlash(slash);
    window.setTimeout(() => setCopiedSlash(null), 1600);
  };

  const workspaceBinding =
    session?.run?.workspace_binding &&
    typeof session.run.workspace_binding === "object"
      ? session.run.workspace_binding
      : null;

  const allAgentsOk =
    healthAgents.length > 0 && healthAgents.every((h) => h.ready);

  return (
    <div className="settings-page">
      <header className="settings-page__header">
        <button type="button" className="btn" onClick={onBack}>
          ← 워크스페이스
        </button>
        <div className="settings-page__heading">
          <h1 className="settings-page__title">설정</h1>
          <p className="settings-page__sub">
            에이전트 · API 키 · 워크스페이스 · 명령 · 진단 · 테마 · 레거시
          </p>
        </div>
      </header>

      <div className="settings-page__body scroll-y">
        <section className="settings-section">
          <div className="settings-section__head">
            <h2 className="settings-section__title">
              <SettingsSectionIcon name="users" />
              에이전트
            </h2>
            <span className="settings-section__sub">
              Health · 작업 폴더 · 도구 · 권한
            </span>
          </div>

          <div className="settings-health">
            {healthAgents.map((h) => (
              <div key={h.id} className="settings-health__row">
                <Avatar role={h.id as AgentRole} size={20} />
                <div className="settings-health__info">
                  <span className="settings-health__name">{h.label}</span>
                  <span className="settings-health__model">
                    {h.model ?? (h.configured ? "설정됨" : "미설정")}
                  </span>
                </div>
                <span
                  className={`dot dot--${h.ready ? "ok dot--live" : "warn"}`}
                  aria-hidden
                />
                <span className={`badge badge--${h.ready ? "ok" : "danger"}`}>
                  {h.ready ? "정상" : "오류"}
                </span>
              </div>
            ))}
          </div>

          {onRefreshDiagnostics || onReconnectCursor ? (
            <div className="settings-health__actions">
              {onRefreshDiagnostics ? (
                <button
                  type="button"
                  className="btn btn--sm"
                  disabled={healthLoading || reconnecting}
                  onClick={onRefreshDiagnostics}
                >
                  {healthLoading ? "…" : "상태 새로고침"}
                </button>
              ) : null}
              {onReconnectCursor ? (
                <button
                  type="button"
                  className="btn btn--sm"
                  disabled={healthLoading || reconnecting}
                  onClick={onReconnectCursor}
                >
                  {reconnecting ? "재연결…" : "Cursor 재연결"}
                </button>
              ) : null}
            </div>
          ) : null}

          <div className="settings-permissions">
            <p className="settings-permissions__hint">
              {permissionDefaultsSaved
                ? "전송 시 권한 확인을 건너뛰는 저장된 기본값이 있습니다."
                : "전송 시 에이전트 권한을 매번 확인합니다."}
            </p>
            {permissionDefaultsSaved ? (
              <button
                type="button"
                className="btn btn--sm"
                onClick={() => {
                  clearSavedPermissionDefaults();
                  setPermissionDefaultsSaved(false);
                }}
              >
                저장된 권한 초기화
              </button>
            ) : null}
          </div>

          <button
            type="button"
            className="settings-expand-btn"
            aria-expanded={agentSettingsOpen}
            onClick={() => setAgentSettingsOpen((v) => !v)}
          >
            {agentSettingsOpen ? "▾" : "▸"} 에이전트별 세션 설정 (작업 폴더·도구)
            <span className="settings-expand-btn__hint">
              Cursor: execute · Codex: repo · Claude: review
            </span>
          </button>

          {agentSettingsOpen ? (
            <>
              <AgentSessionSettings
                capabilities={capabilities}
                onChange={setCapabilities}
                resolvedCwd={resolvedCwd}
                selectedAgents={selectedAgents}
                hideToggle
                onSave={sessionId ? () => void saveCapabilities() : undefined}
                saveBusy={saveBusy}
                saveHint={saveHint ?? undefined}
              />
              {saveHint ? <p className="settings-save-hint">{saveHint}</p> : null}
            </>
          ) : null}
        </section>

        <section className="settings-section">
          <div className="settings-section__head">
            <h2 className="settings-section__title">
              <SettingsSectionIcon name="key" />
              API 키
            </h2>
            <span className="settings-section__sub">
              메인 · 서브 계정 · ~/.agent-lab/credentials.toml
            </span>
          </div>
          <AgentCredentialsPanel />
        </section>

        {sessionId ? (
          <section className="settings-section">
            <div className="settings-section__head">
              <h2 className="settings-section__title">
                <SettingsSectionIcon name="folder" />
                워크스페이스
              </h2>
              <span className="settings-section__sub">
                세션 binding · Context 미리보기
              </span>
            </div>
            <dl className="settings-workspace-info">
              <div className="settings-workspace-info__row">
                <dt>세션</dt>
                <dd>{session?.topic ?? sessionId}</dd>
              </div>
              <div className="settings-workspace-info__row">
                <dt>바인딩</dt>
                <dd>
                  {workspaceBinding
                    ? JSON.stringify(workspaceBinding)
                    : "기본 워크스페이스 프리셋 사용"}
                </dd>
              </div>
              <div className="settings-workspace-info__row">
                <dt>Execute cwd</dt>
                <dd>
                  worktree 격리 가능 시 별도 worktree에서 실행됩니다.
                </dd>
              </div>
            </dl>
            <div className="settings-section__sub-head">Context 미리보기</div>
            <div className="ctx-preview ctx-preview--embedded">
              <ContextPreviewPanel
                sessionId={sessionId}
                session={session}
                selectedAgents={selectedAgents}
                turnProfile={turnProfile}
                efficiencyOn={efficiencyOn}
                embedded
              />
            </div>
          </section>
        ) : null}

        {sessionId ? (
          <section className="settings-section">
            <div className="settings-section__head">
              <h2 className="settings-section__title">
                <SettingsSectionIcon name="terminal" />
                명령 · 플러그인
              </h2>
              <span className="settings-section__sub">
                슬래시 명령 · agent 소스 · 활성 상태
              </span>
            </div>
            <SlashCommandGroupList
              commands={commands}
              onCopy={(slash) => void copySlash(slash)}
              copiedSlash={copiedSlash}
              maxPerAgentGroup={24}
            />
            <p className="settings-hint">
              외부 명령: ~/.agent-lab/tools.yaml ·{" "}
              <code>AGENT_LAB_EXTERNAL_TOOLS=1</code> · 플러그인 탭 External에서 세션 allowlist
            </p>
            <div className="settings-section__sub-head">플러그인</div>
            <PluginPanel
              sessionId={sessionId}
              commands={commands}
              onPrefillSlash={(slash) => void copySlash(slash)}
            />
          </section>
        ) : (
          <section className="settings-section">
            <p className="settings-hint">
              세션을 선택하면 Context 미리보기와 플러그인 설정을 사용할 수 있습니다.
            </p>
          </section>
        )}

        <section className="settings-section">
          <div className="settings-section__head">
            <h2 className="settings-section__title">
              <SettingsSectionIcon name="activity" />
              진단
            </h2>
            <span className="settings-section__sub">
              API health · bridge 상태 · JSON 진단
            </span>
          </div>
          <div
            className={`diag-bar__status diag-bar__status--${apiOk && allAgentsOk ? "ok" : "fail"}`}
          >
            <span
              className={`dot dot--${apiOk && allAgentsOk ? "ok dot--live" : "warn"}`}
              aria-hidden
            />
            {apiOk && allAgentsOk
              ? "API 연결됨 · 모든 에이전트 정상"
              : "일부 연결 또는 에이전트 문제 있음"}
          </div>
          <ApiDiagnosticsBar
            apiOk={apiOk}
            sessionsDir={sessionsDir}
            probeBridgeFailed={probeBridgeFailed}
          />
        </section>

        <section className="settings-section settings-section--split">
          <div>
            <div className="settings-section__head">
              <h2 className="settings-section__title">
                <SettingsSectionIcon name="sun" />
                {t("appearance")}
              </h2>
              <span className="settings-section__sub">
                {t("settingsLanguageSub")}
              </span>
            </div>
            <div className="settings-appearance">
              <div className="settings-appearance__row">
                <span className="settings-appearance__label">
                  {t("settingsLanguage")}
                </span>
                <div className="turn-seg" role="radiogroup" aria-label={t("settingsLanguage")}>
                  {(["en", "ko"] as const).map((code) => (
                    <button
                      key={code}
                      type="button"
                      role="radio"
                      aria-checked={locale === code}
                      className={locale === code ? "is-active" : undefined}
                      onClick={() => setLocale(code)}
                    >
                      {localeLabel(code)}
                    </button>
                  ))}
                </div>
              </div>
              <div className="settings-appearance__row">
                <span className="settings-appearance__label">{t("theme")}</span>
                <ThemeToggle />
              </div>
            </div>
            <p className="settings-hint">
              P0/P1 상태 변화는 toast + Inspector Activity에 함께 기록됩니다.
            </p>
          </div>
          <div>
            <div className="settings-section__head">
              <h2 className="settings-section__title">
                <SettingsSectionIcon name="activity" />
                개발 · QA
              </h2>
              <span className="settings-section__sub">
                오버레이 · 배너 · 알림 UI 미리보기
              </span>
            </div>
            <p className="settings-hint">
              Tweaks 패널에서 Command Palette, MacAlert, 토스트, ExecuteQueueBar 등을
              시뮬레이션합니다. ⌘⇧T 로도 열 수 있습니다.
            </p>
            <TweaksSettingsActions onBack={onBack} />
          </div>
          <div>
            <div className="settings-section__head">
              <h2 className="settings-section__title">
                <SettingsSectionIcon name="archive" />
                레거시
              </h2>
              <span className="settings-section__sub">
                Classic 모드 (Planner→Critic→Scribe)
              </span>
            </div>
            <p className="settings-hint">
              새 작업은 Room 모드를 권장합니다. Classic은 참고용.
            </p>
            <button
              type="button"
              className="btn"
              onClick={onOpenLegacy}
              disabled={!onOpenLegacy}
            >
              클래식(레거시) 열기
            </button>
          </div>
        </section>
      </div>
    </div>
  );
}
