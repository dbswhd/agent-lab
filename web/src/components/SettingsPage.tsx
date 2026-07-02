import { useCallback, useEffect, useState } from "react";
import type { SessionDetail } from "../api/client";
import {
  fetchCommands,
  fetchSessionAgentCapabilities,
  patchSessionAgentCapabilities,
  type AgentHealthRow,
  type SlashCommandRecord,
} from "../api/client";
import { ProviderStatusPanel } from "./ProviderStatusPanel";
import { CodexProxyPanel } from "./CodexProxyPanel";
import { AgentHealthPanel } from "./AgentHealthPanel";
import { AgentSessionSettings } from "./AgentSessionSettings";
import { ApiDiagnosticsBar } from "./ApiDiagnosticsBar";
import { ContextPreviewPanel } from "./ContextPreviewPanel";
import { PluginPanel } from "./PluginPanel";
import { SlashCommandGroupList } from "./SlashCommandGroupList";
import { HooksResponseSettings } from "./HooksResponseSettings";
import { DaemonStatusBar } from "./DaemonStatusBar";
import { GatewaySettingsPanel } from "./GatewaySettingsPanel";
import { SchedulesPanel } from "./SchedulesPanel";
import { ThemeToggle } from "./ThemeToggle";
import { useTweaksDemo } from "../hooks/useTweaksDemo";
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

type Props = {
  sessionId: string | null;
  session: SessionDetail | null;
  selectedAgents: string[];
  turnProfile: ComposerTurnProfile;
  onBack: () => void;
  apiOk?: boolean;
  healthAgents?: AgentHealthRow[];
  healthLoading?: boolean;
  reconnecting?: boolean;
  sessionsDir?: string | null;
  probeBridgeFailed?: boolean;
  onRefreshDiagnostics?: () => void;
  onReconnectCursor?: () => void;
  onReconnectClaude?: () => void;
  onReconnectKimiWork?: () => void;
};

type SettingsCategory =
  | "general"
  | "agents"
  | "connections"
  | "workspace"
  | "automation"
  | "advanced";

const SETTINGS_CATEGORIES: readonly {
  id: SettingsCategory;
  label: string;
}[] = [
  { id: "general", label: "일반" },
  { id: "agents", label: "에이전트" },
  { id: "connections", label: "계정" },
  { id: "workspace", label: "워크스페이스" },
  { id: "automation", label: "자동화" },
  { id: "advanced", label: "진단" },
];

const LEGACY_CATEGORY: Record<string, SettingsCategory> = {
  session: "workspace",
};

function normalizeCategory(raw: string | null): SettingsCategory {
  if (raw && SETTINGS_CATEGORIES.some((item) => item.id === raw)) {
    return raw as SettingsCategory;
  }
  if (raw && raw in LEGACY_CATEGORY) {
    return LEGACY_CATEGORY[raw]!;
  }
  return "general";
}

function TweaksSettingsActions({ onBack }: { onBack: () => void }) {
  const tweaks = useTweaksDemo();
  return (
    <button
      type="button"
      className="btn btn--sm btn--ghost"
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
  onBack,
  apiOk = true,
  healthAgents = [],
  healthLoading,
  reconnecting,
  sessionsDir = null,
  probeBridgeFailed = false,
  onRefreshDiagnostics,
  onReconnectCursor,
  onReconnectClaude,
  onReconnectKimiWork,
}: Props) {
  const { locale, setLocale, t } = useLocale();
  const [capabilities, setCapabilities] = useState<AgentCapabilitiesMap>(() =>
    cloneCapabilities(DEFAULT_AGENT_CAPABILITIES),
  );
  const [resolvedCwd, setResolvedCwd] = useState<Record<string, string>>({});
  const [saveBusy, setSaveBusy] = useState(false);
  const [saveHint, setSaveHint] = useState<string | null>(null);
  const [commands, setCommands] = useState<SlashCommandRecord[]>([]);
  const [copiedSlash, setCopiedSlash] = useState<string | null>(null);
  const [permissionDefaultsSaved, setPermissionDefaultsSaved] = useState(
    hasSavedPermissionDefaults,
  );
  const [category, setCategory] = useState<SettingsCategory>(() =>
    normalizeCategory(
      window.localStorage.getItem("agent-lab.settings-category"),
    ),
  );

  const selectCategory = (next: SettingsCategory) => {
    setCategory(next);
    window.localStorage.setItem("agent-lab.settings-category", next);
  };

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
      setSaveHint("저장됨");
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

  return (
    <div className="settings-page" data-settings-category={category}>
      <header className="settings-page__header">
        <button type="button" className="btn btn--ghost" onClick={onBack}>
          ← 돌아가기
        </button>
        <h1 className="settings-page__title">설정</h1>
      </header>

      <div className="settings-category-mobile">
        <select
          id="settings-category"
          aria-label="설정 카테고리"
          value={category}
          onChange={(event) =>
            selectCategory(event.target.value as SettingsCategory)
          }
        >
          {SETTINGS_CATEGORIES.map((item) => (
            <option key={item.id} value={item.id}>
              {item.label}
            </option>
          ))}
        </select>
      </div>

      <nav className="settings-category-nav" aria-label="설정 카테고리">
        {SETTINGS_CATEGORIES.map((item) => (
          <button
            key={item.id}
            type="button"
            className={category === item.id ? "is-active" : undefined}
            aria-current={category === item.id ? "page" : undefined}
            onClick={() => selectCategory(item.id)}
          >
            {item.label}
          </button>
        ))}
      </nav>

      <div className="settings-page__body scroll-y">
        <section className="settings-panel settings-panel--general">
          <div className="settings-appearance">
            <div className="settings-appearance__row">
              <span className="settings-appearance__label">
                {t("settingsLanguage")}
              </span>
              <div
                className="turn-seg"
                role="radiogroup"
                aria-label={t("settingsLanguage")}
              >
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
        </section>

        <section className="settings-panel settings-panel--agents">
          <AgentHealthPanel
            apiOk={apiOk}
            agents={healthAgents}
            loading={healthLoading}
            reconnecting={reconnecting}
            showBridgeSetupGuide={probeBridgeFailed}
            onRefresh={onRefreshDiagnostics}
            onReconnectCursor={onReconnectCursor}
            onReconnectClaude={onReconnectClaude}
            onReconnectKimiWork={onReconnectKimiWork}
          />
          <div className="settings-block">
            <h3 className="settings-block__title">작업 폴더 · 도구</h3>
            {sessionId ? (
              <AgentSessionSettings
                embedded
                compact
                capabilities={capabilities}
                onChange={setCapabilities}
                resolvedCwd={resolvedCwd}
                selectedAgents={selectedAgents}
                hideToggle
                onSave={() => void saveCapabilities()}
                saveBusy={saveBusy}
                saveHint={saveHint ?? undefined}
              />
            ) : (
              <p className="settings-hint">세션 선택 후 편집할 수 있습니다.</p>
            )}
          </div>
          {permissionDefaultsSaved ? (
            <button
              type="button"
              className="btn btn--sm btn--ghost"
              onClick={() => {
                clearSavedPermissionDefaults();
                setPermissionDefaultsSaved(false);
              }}
            >
              저장된 권한 초기화
            </button>
          ) : null}
        </section>

        <section className="settings-panel settings-panel--connections">
          <ProviderStatusPanel embedded />
          <CodexProxyPanel embedded />
        </section>

        <section className="settings-panel settings-panel--workspace">
          {sessionId ? (
            <>
              <p className="settings-inline-note">
                {session?.topic ?? sessionId}
              </p>
              <details className="settings-details">
                <summary>Context</summary>
                <div className="ctx-preview ctx-preview--embedded">
                  <ContextPreviewPanel
                    sessionId={sessionId}
                    session={session}
                    selectedAgents={selectedAgents}
                    turnProfile={turnProfile}
                    embedded
                  />
                </div>
              </details>
              <details className="settings-details">
                <summary>슬래시 명령</summary>
                <SlashCommandGroupList
                  commands={commands}
                  onCopy={(slash) => void copySlash(slash)}
                  copiedSlash={copiedSlash}
                  maxPerAgentGroup={8}
                />
              </details>
              <details className="settings-details">
                <summary>플러그인</summary>
                <PluginPanel
                  compact
                  sessionId={sessionId}
                  commands={commands}
                  onPrefillSlash={(slash) => void copySlash(slash)}
                />
              </details>
            </>
          ) : (
            <p className="settings-hint">세션을 선택하면 표시됩니다.</p>
          )}
        </section>

        <section className="settings-panel settings-panel--automation">
          <DaemonStatusBar embedded />
          <details className="settings-details">
            <summary>Gateway · webhook</summary>
            <GatewaySettingsPanel embedded />
          </details>
          {sessionId ? (
            <details className="settings-details">
              <summary>스케줄</summary>
              <SchedulesPanel sessionId={sessionId} />
            </details>
          ) : null}
          <div className="settings-block">
            <h3 className="settings-block__title">
              응답 형식 (Response contract)
            </h3>
            <p className="settings-block__hint">
              에이전트 답변 형식입니다. 역할·관점 배정(role plan)과는
              별개입니다.
            </p>
            <HooksResponseSettings
              embedded
              sessionId={sessionId}
              session={session}
            />
          </div>
        </section>

        <section className="settings-panel settings-panel--advanced">
          <ApiDiagnosticsBar
            compact
            apiOk={apiOk}
            sessionsDir={sessionsDir}
            probeBridgeFailed={probeBridgeFailed}
          />
          <TweaksSettingsActions onBack={onBack} />
        </section>
      </div>
    </div>
  );
}
