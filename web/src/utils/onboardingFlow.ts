import type { AgentHealthRow } from "../api/client";

export type OnboardingStepId =
  | "connect_agents"
  | "choose_workspace"
  | "start_sample";

export type OnboardingActionId =
  | "open_settings"
  | "refresh_health"
  | "reconnect_cursor"
  | "reconnect_claude"
  | "choose_workspace"
  | "start_sample"
  | "dismiss";

export type OnboardingStepStatus = "complete" | "active" | "blocked";

export type OnboardingStep = {
  readonly id: OnboardingStepId;
  readonly status: OnboardingStepStatus;
  readonly title: string;
  readonly summary: string;
  readonly why: string;
  readonly blockedBy: string;
  readonly primaryAction: OnboardingActionId;
  readonly secondaryAction: OnboardingActionId;
};

export type OnboardingSummary = {
  readonly readyAgentCount: number;
  readonly hasReadyAgent: boolean;
  readonly hasWorkspace: boolean;
  readonly canStartSample: boolean;
  readonly steps: readonly OnboardingStep[];
};

export type OnboardingSummaryInput = {
  readonly apiOk: boolean;
  readonly agents: readonly AgentHealthRow[];
  readonly hasWorkspace: boolean;
};

function readyCount(agents: readonly AgentHealthRow[]): number {
  return agents.filter((agent) => agent.ready).length;
}

export function onboardingSummary({
  apiOk,
  agents,
  hasWorkspace,
}: OnboardingSummaryInput): OnboardingSummary {
  const count = readyCount(agents);
  const hasReadyAgent = apiOk && count > 0;
  const canStartSample = hasReadyAgent && hasWorkspace;

  return {
    readyAgentCount: count,
    hasReadyAgent,
    hasWorkspace,
    canStartSample,
    steps: [
      {
        id: "connect_agents",
        status: hasReadyAgent ? "complete" : "active",
        title: "Connect agents",
        summary: hasReadyAgent ? `${count}/3 ready` : "연결할 agent 필요",
        why: "Room은 최소 한 에이전트가 준비되어야 plan.md를 만들 수 있습니다.",
        blockedBy: apiOk
          ? "Codex, Claude, Cursor 중 하나 이상을 연결하세요."
          : "API가 offline이라 agent 상태를 확인할 수 없습니다.",
        primaryAction: "refresh_health",
        secondaryAction: "open_settings",
      },
      {
        id: "choose_workspace",
        status: hasWorkspace ? "complete" : "active",
        title: "Choose workspace",
        summary: hasWorkspace ? "작업 폴더 준비됨" : "작업 폴더 선택 필요",
        why: "에이전트가 읽고 실행할 프로젝트 루트를 먼저 고정해야 합니다.",
        blockedBy: "New Session에서 최근 폴더나 다른 폴더를 선택하세요.",
        primaryAction: "choose_workspace",
        secondaryAction: "open_settings",
      },
      {
        id: "start_sample",
        status: canStartSample
          ? "active"
          : hasWorkspace
            ? "blocked"
            : "blocked",
        title: "Start sample session",
        summary: canStartSample ? "샘플 주제 준비 가능" : "앞 단계 완료 필요",
        why: "샘플 세션은 Room -> plan.md -> Human 승인 흐름을 안전하게 확인합니다.",
        blockedBy: canStartSample
          ? "샘플 topic을 채운 뒤 사용자가 직접 전송합니다."
          : "agent 연결과 workspace 선택이 모두 필요합니다.",
        primaryAction: "start_sample",
        secondaryAction: "dismiss",
      },
    ],
  };
}
