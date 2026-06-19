import type { AgentHealthRow } from "../api/client";
import {
  onboardingSummary,
  type OnboardingActionId,
  type OnboardingStep,
} from "../utils/onboardingFlow";

type Props = {
  readonly apiOk: boolean;
  readonly healthText: string;
  readonly agents: readonly AgentHealthRow[];
  readonly loading: boolean;
  readonly sessionsDir: string | null;
  readonly hasWorkspace: boolean;
  readonly onRefresh: () => void;
  readonly onOpenSettings: () => void;
  readonly onReconnectCursor: () => void;
  readonly onReconnectClaude: () => void;
  readonly onChooseWorkspace: () => void;
  readonly onStartSample: () => void;
  readonly onSkip: () => void;
};

const AGENT_ORDER = ["cursor", "codex", "claude"] as const;

function agentStatusLabel(agent: AgentHealthRow | undefined): string {
  if (!agent) return "확인 대기";
  if (agent.ready) return "연결됨";
  if (agent.configured) return "재확인 필요";
  return "설정 필요";
}

function agentDetail(agent: AgentHealthRow | undefined): string {
  if (!agent) return "Health probe가 아직 도착하지 않았습니다.";
  if (agent.ready) return agent.model ?? "Room에 참여할 수 있습니다.";
  if (agent.configured) return "설정은 있지만 실행 확인이 필요합니다.";
  return "인증 또는 CLI 경로 설정이 필요합니다.";
}

function nextCommand(agentId: string): string | null {
  switch (agentId) {
    case "cursor":
      return "CURSOR_API_KEY 또는 Cursor SDK bridge";
    case "codex":
      return "codex login";
    case "claude":
      return "claude login";
    default:
      return "Settings에서 연결 상태 확인";
  }
}

function actionLabel(actionId: OnboardingActionId): string {
  switch (actionId) {
    case "open_settings":
      return "Settings";
    case "refresh_health":
      return "Health refresh";
    case "reconnect_cursor":
      return "Cursor reconnect";
    case "reconnect_claude":
      return "Claude reconnect";
    case "choose_workspace":
      return "Workspace 선택";
    case "start_sample":
      return "샘플 세션";
    case "dismiss":
      return "나중에";
  }
}

function stepBadgeClass(step: OnboardingStep): string {
  switch (step.status) {
    case "complete":
      return "badge--ok";
    case "active":
      return "badge--accent";
    case "blocked":
      return "badge--warn";
  }
}

function stepBadgeLabel(step: OnboardingStep): string {
  switch (step.status) {
    case "complete":
      return "done";
    case "active":
      return "next";
    case "blocked":
      return "blocked";
  }
}

function StepCard({
  step,
  index,
  onAction,
}: {
  readonly step: OnboardingStep;
  readonly index: number;
  readonly onAction: (actionId: OnboardingActionId) => void;
}) {
  return (
    <li className={`first-run__step first-run__step--${step.status}`}>
      <div className="first-run__step-head">
        <span className="first-run__step-index">{index}</span>
        <div>
          <strong>{step.title}</strong>
          <span>{step.summary}</span>
        </div>
        <span className={`badge ${stepBadgeClass(step)}`}>
          {stepBadgeLabel(step)}
        </span>
      </div>
      <p className="first-run__copy">{step.why}</p>
      <p className="first-run__blocker">{step.blockedBy}</p>
      <div className="first-run__step-actions">
        <button
          type="button"
          className="btn btn--sm btn--primary"
          onClick={() => onAction(step.primaryAction)}
          disabled={step.status === "blocked"}
        >
          {actionLabel(step.primaryAction)}
        </button>
        <button
          type="button"
          className="btn btn--sm"
          onClick={() => onAction(step.secondaryAction)}
        >
          {actionLabel(step.secondaryAction)}
        </button>
      </div>
    </li>
  );
}

export function FirstRunOnboarding({
  apiOk,
  healthText,
  agents,
  loading,
  sessionsDir,
  hasWorkspace,
  onRefresh,
  onOpenSettings,
  onReconnectCursor,
  onReconnectClaude,
  onChooseWorkspace,
  onStartSample,
  onSkip,
}: Props) {
  const summary = onboardingSummary({ apiOk, agents, hasWorkspace });

  function handleAction(actionId: OnboardingActionId) {
    switch (actionId) {
      case "open_settings":
        onOpenSettings();
        return;
      case "refresh_health":
        onRefresh();
        return;
      case "reconnect_cursor":
        onReconnectCursor();
        return;
      case "reconnect_claude":
        onReconnectClaude();
        return;
      case "choose_workspace":
        onChooseWorkspace();
        return;
      case "start_sample":
        onStartSample();
        return;
      case "dismiss":
        onSkip();
        return;
    }
  }

  return (
    <main className="first-run" aria-labelledby="first-run-title">
      <section className="first-run__panel">
        <header className="first-run__header">
          <span className="first-run__eyebrow">Setup wizard</span>
          <h2 id="first-run-title">Agent Lab 시작 준비</h2>
          <p>
            AI 개발 작업을 plan.md로 정리하고 Human 승인 뒤 worktree에서
            실행·검증하려면 agent, workspace, sample session을 먼저 확인합니다.
          </p>
        </header>

        <div className="first-run__status">
          <span
            className={`first-run__api-dot${apiOk ? " first-run__api-dot--ok" : ""}`}
            aria-hidden="true"
          />
          <div>
            <strong>{apiOk ? "API online" : "API offline"}</strong>
            <span>{healthText || "health probe 대기 중"}</span>
          </div>
          <button
            type="button"
            className="btn btn--sm"
            onClick={onRefresh}
            disabled={loading}
          >
            새로고침
          </button>
        </div>

        <ol className="first-run__steps">
          <li className="first-run__step first-run__step--agents">
            <div className="first-run__step-head">
              <span className="first-run__step-index">1</span>
              <div>
                <strong>Connect agents</strong>
                <span>
                  {summary.readyAgentCount}/{agents.length} ready
                </span>
              </div>
            </div>
            <div className="first-run__agents">
              {AGENT_ORDER.map((id) => {
                const agent = agents.find((row) => row.id === id);
                const ready = Boolean(agent?.ready);
                return (
                  <div
                    key={id}
                    className={`first-run-agent${ready ? " first-run-agent--ready" : ""}`}
                  >
                    <span className="first-run-agent__name">
                      {agent?.label ?? id}
                    </span>
                    <span className="first-run-agent__status">
                      {agentStatusLabel(agent)}
                    </span>
                    <span className="first-run-agent__detail">
                      {agentDetail(agent)}
                    </span>
                    {!ready ? (
                      <code className="first-run-agent__cmd">
                        {nextCommand(id)}
                      </code>
                    ) : null}
                    {id === "cursor" && !ready ? (
                      <button
                        type="button"
                        className="btn btn--sm"
                        onClick={onReconnectCursor}
                      >
                        재연결
                      </button>
                    ) : null}
                    {id === "codex" && !ready ? (
                      <button
                        type="button"
                        className="btn btn--sm"
                        onClick={onOpenSettings}
                      >
                        Settings
                      </button>
                    ) : null}
                    {id === "claude" && !ready ? (
                      <button
                        type="button"
                        className="btn btn--sm"
                        onClick={onReconnectClaude}
                      >
                        재연결
                      </button>
                    ) : null}
                  </div>
                );
              })}
            </div>
            <p className="first-run__copy">
              Room은 최소 한 에이전트가 준비되어야 plan.md를 만들 수 있습니다.
            </p>
            <p className="first-run__blocker">
              {summary.hasReadyAgent
                ? "필요하면 나머지 agent도 연결해 팀 품질을 높일 수 있습니다."
                : apiOk
                  ? "Codex, Claude, Cursor 중 하나 이상을 연결하세요."
                  : "API가 offline이라 agent 상태를 확인할 수 없습니다."}
            </p>
            <div className="first-run__step-actions">
              <button
                type="button"
                className="btn btn--sm btn--primary"
                onClick={onRefresh}
                disabled={loading}
              >
                Health refresh
              </button>
              <button
                type="button"
                className="btn btn--sm"
                onClick={onOpenSettings}
              >
                Settings
              </button>
            </div>
          </li>

          {summary.steps.slice(1).map((step, index) => (
            <StepCard
              key={step.id}
              step={step}
              index={index + 2}
              onAction={handleAction}
            />
          ))}
        </ol>

        <footer className="first-run__actions">
          <span className="first-run__footnote" title={sessionsDir ?? ""}>
            {sessionsDir ? `sessions: ${sessionsDir}` : "sessions 폴더 확인 중"}
          </span>
          <button type="button" className="btn" onClick={onSkip}>
            건너뛰기
          </button>
          <button type="button" className="btn" onClick={onOpenSettings}>
            Settings 열기
          </button>
          <button
            type="button"
            className="btn btn--primary"
            onClick={onStartSample}
            disabled={!summary.canStartSample}
          >
            샘플 세션 만들기
          </button>
        </footer>
      </section>
    </main>
  );
}
