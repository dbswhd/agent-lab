import type { AgentCapabilitiesMap } from "../utils/agentCapabilities";

type Props = {
  capabilities: AgentCapabilitiesMap;
  resolvedCwd: Record<string, string>;
  selectedAgents: string[];
  onOpenFullSettings?: () => void;
};

export function QuickSettingsPanel({
  capabilities,
  resolvedCwd,
  selectedAgents,
  onOpenFullSettings,
}: Props) {
  const cwdPreview = selectedAgents
    .map((id) => `${id}: ${resolvedCwd[id] ?? "—"}`)
    .join("\n");

  return (
    <div className="quick-settings-panel">
      <p className="quick-settings-panel__lead">
        자주 쓰는 설정만 표시합니다. Context·Plugin·상세 agent 설정은 설정
        페이지에서 관리하세요.
      </p>
      <div className="quick-settings-panel__block">
        <strong>선택 에이전트</strong>
        <span>{selectedAgents.join(" · ") || "—"}</span>
      </div>
      <div className="quick-settings-panel__block">
        <strong>작업 디렉터리</strong>
        <pre className="quick-settings-panel__cwd">{cwdPreview || "—"}</pre>
      </div>
      <div className="quick-settings-panel__block">
        <strong>도구</strong>
        <span>
          {selectedAgents
            .map((id) => {
              const cap = capabilities[id as keyof AgentCapabilitiesMap];
              return cap ? `${id}(${cap.tools.length})` : id;
            })
            .join(" · ") || "—"}
        </span>
      </div>
      {onOpenFullSettings ? (
        <button
          type="button"
          className="mac-btn-secondary quick-settings-panel__open"
          onClick={onOpenFullSettings}
        >
          전체 설정 열기…
        </button>
      ) : null}
    </div>
  );
}
