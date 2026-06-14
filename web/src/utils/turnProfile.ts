export type ComposerTurnProfile =
  | "quick"
  | "team"
  | "loop"
  | "analyze"
  | "review"
  | "free"
  | "specialist"
  | "verified";

export type TurnProfileConfig = {
  agentRounds: number;
  reviewMode: boolean;
  singleAgent: boolean;
  consensusMode: boolean;
};

const STORAGE_KEY = "agent-lab-turn-profile";

export function turnStrategyOptions(locale: "en" | "ko" = "en") {
  const ko = locale === "ko";
  return [
    {
      id: "quick" as const,
      label: ko ? "빠른" : "Quick",
      description: ko
        ? "에이전트 1명 · R1 · plan 선택"
        : "1 agent · R1 · optional plan",
    },
    {
      id: "team" as const,
      label: ko ? "팀" : "Team",
      description: ko
        ? "3명 병렬 · R1 · plan 선택"
        : "3 agents · R1 · optional plan",
    },
    {
      id: "loop" as const,
      label: ko ? "루프" : "Loop",
      description: ko
        ? "3명 · plan 필수 · 실행/검증 게이트"
        : "3 agents · plan required · execute/verify gates",
    },
  ];
}

export const TURN_STRATEGY_OPTIONS = turnStrategyOptions("en");

export function composerTurnHint(
  profile: ComposerTurnProfile,
  selectedAgents: string[],
  locale: "en" | "ko" = "en",
): string {
  const normalized = normalizeTurnProfile(profile);
  const resolved = resolveTurnSend(normalized, selectedAgents);
  const n = resolved.agents.length;
  const ko = locale === "ko";
  if (normalized === "quick") {
    const lead = selectedAgents[0] ?? "agent";
    return ko
      ? selectedAgents.length > 1
        ? `빠른 · ${lead}만 · R1`
        : "빠른 · R1"
      : selectedAgents.length > 1
        ? `Quick · ${lead} only · R1`
        : "Quick · R1";
  }
  if (normalized === "team") {
    return ko
      ? `팀 · ${n}명 · R1 · plan 선택`
      : `Team · ${n} agents · R1 · optional plan`;
  }
  return ko
    ? `루프 · ${n}명 · plan 필수 · 검증 게이트`
    : `Loop · ${n} agents · plan required · verify gates`;
}

export const TURN_PROFILE_OPTIONS: {
  id: ComposerTurnProfile;
  label: string;
  description: string;
}[] = [...TURN_STRATEGY_OPTIONS];

export function normalizeTurnProfile(
  profile: string | null | undefined,
): ComposerTurnProfile {
  if (profile === "quick") return "quick";
  if (profile === "team") return "team";
  if (profile === "loop") return "loop";
  if (profile === "analyze") return "team";
  if (profile === "discuss") return "team";
  if (profile === "free") return "loop";
  if (profile === "review") return "loop";
  if (profile === "verified") return "loop";
  if (profile === "specialist") return "loop";
  if (profile === "split") return "loop";
  if (profile === "infinity") return "loop";
  return "team";
}

export function turnProfileDescription(profile: ComposerTurnProfile): string {
  const normalized = normalizeTurnProfile(profile);
  return (
    turnStrategyOptions("en").find((o) => o.id === normalized)?.description ??
    TURN_PROFILE_OPTIONS.find((o) => o.id === profile)?.description ??
    ""
  );
}

export const TURN_PROFILE_CONFIG: Record<
  ComposerTurnProfile,
  TurnProfileConfig
> = {
  quick: {
    agentRounds: 1,
    reviewMode: false,
    singleAgent: true,
    consensusMode: false,
  },
  team: {
    agentRounds: 1,
    reviewMode: false,
    singleAgent: false,
    consensusMode: false,
  },
  loop: {
    agentRounds: 1,
    reviewMode: false,
    singleAgent: false,
    consensusMode: true,
  },
  analyze: {
    agentRounds: 1,
    reviewMode: false,
    singleAgent: false,
    consensusMode: false,
  },
  specialist: {
    agentRounds: 2,
    reviewMode: false,
    singleAgent: false,
    consensusMode: false,
  },
  verified: {
    agentRounds: 1,
    reviewMode: false,
    singleAgent: false,
    consensusMode: false,
  },
  review: {
    agentRounds: 1,
    reviewMode: false,
    singleAgent: false,
    consensusMode: true,
  },
  free: {
    agentRounds: 1,
    reviewMode: false,
    singleAgent: false,
    consensusMode: true,
  },
};

export function getTurnProfile(): ComposerTurnProfile {
  const stored = localStorage.getItem(STORAGE_KEY);
  const normalized = normalizeTurnProfile(stored);
  if (stored !== normalized) {
    localStorage.setItem(STORAGE_KEY, normalized);
  }
  return normalized;
}

export function setTurnProfile(profile: ComposerTurnProfile): void {
  localStorage.setItem(STORAGE_KEY, normalizeTurnProfile(profile));
}

export function resolveTurnSend(
  profile: ComposerTurnProfile,
  selectedAgents: string[],
): {
  agents: string[];
  agentRounds: number;
  reviewMode: boolean;
  consensusMode: boolean;
} {
  const normalized = normalizeTurnProfile(profile);
  const cfg = TURN_PROFILE_CONFIG[normalized];
  const agents = cfg.singleAgent
    ? selectedAgents.slice(0, 1)
    : [...selectedAgents];
  return {
    agents,
    agentRounds: cfg.agentRounds,
    reviewMode: cfg.reviewMode,
    consensusMode: cfg.consensusMode,
  };
}

export function turnProfileHint(
  profile: ComposerTurnProfile,
  selectedAgents: string[],
): string | null {
  const normalized = normalizeTurnProfile(profile);
  if (normalized === "quick" && selectedAgents.length > 1) {
    return `빠른 · ${selectedAgents[0]}만 · R1`;
  }
  if (normalized === "team") {
    return selectedAgents.length > 1
      ? `팀 · ${selectedAgents.length}명 · R1 · plan 선택`
      : "팀 · R1 · plan 선택";
  }
  return selectedAgents.length > 1
    ? `루프 · ${selectedAgents.length}명 · plan 필수 · 검증`
    : "루프 · plan 필수 · 검증";
}
