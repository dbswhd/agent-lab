import { useCallback, useEffect, useState } from "react";
import type { SessionDetail } from "../api/client";
import {
  fetchCommands,
  fetchSessionAgentCapabilities,
  patchSessionAgentCapabilities,
  type AgentHealthRow,
  type SlashCommandRecord,
} from "../api/client";
import { AgentHealthPanel } from "./AgentHealthPanel";
import { AgentSessionSettings } from "./AgentSessionSettings";
import { ApiDiagnosticsBar } from "./ApiDiagnosticsBar";
import { ContextPreviewPanel } from "./ContextPreviewPanel";
import { PluginPanel } from "./PluginPanel";
import { ThemeToggle } from "./ThemeToggle";
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
  const [capabilities, setCapabilities] = useState<AgentCapabilitiesMap>(
    () => cloneCapabilities(DEFAULT_AGENT_CAPABILITIES),
  );
  const [resolvedCwd, setResolvedCwd] = useState<Record<string, string>>({});
  const [saveBusy, setSaveBusy] = useState(false);
  const [saveHint, setSaveHint] = useState<string | null>(null);
  const [commands, setCommands] = useState<SlashCommandRecord[]>([]);
  const [commandHint, setCommandHint] = useState<string | null>(null);

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
      setCommandHint(`${slash} 복사됨`);
    } catch {
      setCommandHint(`${slash} 사용 가능`);
    }
    window.setTimeout(() => setCommandHint(null), 1800);
  };

  const workspaceBinding =
    session?.run?.workspace_binding && typeof session.run.workspace_binding === "object"
      ? session.run.workspace_binding
      : null;

  return (
    <div className="settings-page">
      <header className="settings-page__header">
        <button type="button" className="mac-btn-secondary" onClick={onBack}>
          ← Workspace
        </button>
        <div>
          <h1 className="settings-page__title">Settings</h1>
          <p className="settings-page__subtitle">
            Agents · Workspace · Commands · Diagnostics · Legacy
          </p>
        </div>
      </header>

      <div className="settings-page__grid">
        <section className="settings-page__section">
          <div className="settings-page__section-head">
            <h2>Agents</h2>
            <span>health · cwd role · tools · permissions</span>
          </div>
          <AgentHealthPanel
            apiOk={apiOk}
            agents={healthAgents}
            loading={healthLoading}
            reconnecting={reconnecting}
            onRefresh={onRefreshDiagnostics}
            onReconnectCursor={onReconnectCursor}
            showBridgeSetupGuide={probeBridgeFailed}
          />
          <AgentSessionSettings
            capabilities={capabilities}
            onChange={setCapabilities}
            resolvedCwd={resolvedCwd}
            selectedAgents={selectedAgents}
            onSave={sessionId ? () => void saveCapabilities() : undefined}
            saveBusy={saveBusy}
            saveHint={saveHint ?? undefined}
          />
        </section>

        {sessionId ? (
          <section className="settings-page__section">
            <div className="settings-page__section-head">
              <h2>Workspace</h2>
              <span>global default와 현재 세션 binding을 분리해서 봅니다.</span>
            </div>
            <dl className="settings-page__workspace">
              <div>
                <dt>Session</dt>
                <dd>{session?.topic ?? sessionId}</dd>
              </div>
              <div>
                <dt>Binding</dt>
                <dd>
                  {workspaceBinding
                    ? JSON.stringify(workspaceBinding)
                    : "기본 workspace preset 사용"}
                </dd>
              </div>
              <div>
                <dt>Discuss / Review / Execute cwd</dt>
                <dd>
                  Agent별 cwd role에서 결정됩니다. Execute는 worktree isolation이
                  가능하면 별도 worktree에서 실행됩니다.
                </dd>
              </div>
            </dl>
            <ContextPreviewPanel
              sessionId={sessionId}
              session={session}
              selectedAgents={selectedAgents}
              turnProfile={turnProfile}
              efficiencyOn={efficiencyOn}
            />
          </section>
        ) : null}

        {sessionId ? (
          <section className="settings-page__section">
            <div className="settings-page__section-head">
              <h2>Commands</h2>
              <span>slash · agent source · enabled 상태 · native add hint</span>
            </div>
            {commandHint ? (
              <p className="settings-page__hint settings-page__hint--success">
                {commandHint}
              </p>
            ) : null}
            <PluginPanel
              sessionId={sessionId}
              commands={commands}
              onPrefillSlash={(slash) => void copySlash(slash)}
            />
          </section>
        ) : (
          <section className="settings-page__section">
            <p className="settings-page__hint">
              세션을 선택하면 Context 미리보기와 Plugin 설정을 사용할 수
              있습니다.
            </p>
          </section>
        )}

        <section className="settings-page__section">
          <div className="settings-page__section-head">
            <h2>Diagnostics</h2>
            <span>API health · bridge status · JSON diagnostics</span>
          </div>
          <ApiDiagnosticsBar
            apiOk={apiOk}
            sessionsDir={sessionsDir}
            probeBridgeFailed={probeBridgeFailed}
          />
        </section>

        <section className="settings-page__section settings-page__section--split">
          <div>
            <div className="settings-page__section-head">
              <h2>Appearance &amp; Notifications</h2>
              <span>작업 본문은 solid, transient chrome만 glass로 유지합니다.</span>
            </div>
            <ThemeToggle />
            <p className="settings-page__hint">
              P0/P1 상태 변화는 toast와 Inspector Activity에 같이 쌓입니다.
            </p>
          </div>
          <div>
            <div className="settings-page__section-head">
              <h2>Legacy</h2>
              <span>기존 room mode 확인용. 새 IA는 Transcript/Work 기준입니다.</span>
            </div>
            <button
              type="button"
              className="mac-btn-secondary"
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
