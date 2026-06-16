import type { AgentHealthRow } from "../api/client";

type Props = {
  readonly apiOk: boolean;
  readonly healthText: string;
  readonly agents: readonly AgentHealthRow[];
  readonly loading: boolean;
  readonly sessionsDir: string | null;
  readonly onRefresh: () => void;
  readonly onOpenSettings: () => void;
  readonly onReconnectCursor: () => void;
  readonly onReconnectClaude: () => void;
  readonly onStartSample: () => void;
  readonly onSkip: () => void;
};

const AGENT_ORDER = ["cursor", "codex", "claude"] as const;

function readyCount(agents: readonly AgentHealthRow[]): number {
  return agents.filter((agent) => agent.ready).length;
}

function agentStatusLabel(agent: AgentHealthRow | undefined): string {
  if (!agent) return "확인 대기";
  if (agent.ready) return "연결됨";
  if (agent.configured) return "재확인 필요";
  return "설정 필요";
}

function agentDetail(agent: AgentHealthRow | undefined): string {
  if (!agent) return "Health probe가 아직 도착하지 않았습니다.";
  return (
    agent.reason ??
    agent.hint ??
    agent.detail ??
    agent.model ??
    "사용 가능합니다."
  );
}

function nextCommand(agentId: string): string {
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

export function FirstRunOnboarding({
  apiOk,
  healthText,
  agents,
  loading,
  sessionsDir,
  onRefresh,
  onOpenSettings,
  onReconnectCursor,
  onReconnectClaude,
  onStartSample,
  onSkip,
}: Props) {
  const count = readyCount(agents);
  const canStart = apiOk && count > 0;

  return (
    <main className="first-run" aria-labelledby="first-run-title">
      <section className="first-run__panel">
        <header className="first-run__header">
          <span className="first-run__eyebrow">First run</span>
          <h2 id="first-run-title">Agent Lab 시작 설정</h2>
          <p>
            에이전트 연결 상태를 확인한 뒤 샘플 세션에서 작업 폴더와 팀을
            선택합니다.
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
          <li className="first-run__step">
            <div className="first-run__step-head">
              <span className="first-run__step-index">1</span>
              <div>
                <strong>에이전트 연결</strong>
                <span>{count}/3 ready</span>
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
          </li>

          <li className="first-run__step">
            <div className="first-run__step-head">
              <span className="first-run__step-index">2</span>
              <div>
                <strong>작업 폴더 선택</strong>
                <span>{sessionsDir ?? "세션 폴더 확인 중"}</span>
              </div>
            </div>
            <p className="first-run__copy">
              샘플 세션을 만들 때 기존 프리셋이나 다른 폴더를 선택합니다.
            </p>
          </li>

          <li className="first-run__step">
            <div className="first-run__step-head">
              <span className="first-run__step-index">3</span>
              <div>
                <strong>샘플 세션 시작</strong>
                <span>Room → plan.md 흐름 확인</span>
              </div>
            </div>
            <p className="first-run__copy">
              샘플 주제가 composer에 채워집니다. 팀과 폴더를 확인한 뒤 전송하면
              첫 Room 턴이 시작됩니다.
            </p>
          </li>
        </ol>

        <footer className="first-run__actions">
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
            disabled={!canStart}
          >
            샘플 세션 만들기
          </button>
        </footer>
      </section>
    </main>
  );
}
