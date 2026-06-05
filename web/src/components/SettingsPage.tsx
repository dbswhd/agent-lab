import { useCallback, useEffect, useState } from "react";
import type { SessionDetail } from "../api/client";
import {
  fetchSessionAgentCapabilities,
  patchSessionAgentCapabilities,
} from "../api/client";
import { AgentSessionSettings } from "./AgentSessionSettings";
import { ContextPreviewPanel } from "./ContextPreviewPanel";
import { PluginPanel } from "./PluginPanel";
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
};

export function SettingsPage({
  sessionId,
  session,
  selectedAgents,
  turnProfile,
  efficiencyOn,
  onBack,
}: Props) {
  const [capabilities, setCapabilities] = useState<AgentCapabilitiesMap>(
    () => cloneCapabilities(DEFAULT_AGENT_CAPABILITIES),
  );
  const [resolvedCwd, setResolvedCwd] = useState<Record<string, string>>({});
  const [saveBusy, setSaveBusy] = useState(false);
  const [saveHint, setSaveHint] = useState<string | null>(null);

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

  return (
    <div className="settings-page">
      <header className="settings-page__header">
        <button type="button" className="mac-btn-secondary" onClick={onBack}>
          ← Workspace
        </button>
        <div>
          <h1 className="settings-page__title">Settings</h1>
          <p className="settings-page__subtitle">
            Agent · Context · Plugins · workspace policy
          </p>
        </div>
      </header>

      <div className="settings-page__grid">
        <section className="settings-page__section">
          <h2>Agents</h2>
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
            <h2>Context</h2>
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
            <h2>Plugins &amp; Commands</h2>
            <PluginPanel
              sessionId={sessionId}
              commands={[]}
              onPrefillSlash={() => {}}
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
      </div>
    </div>
  );
}
