import { setEfficiencyMode } from "./efficiencyPrefs";

export type ComposerTurnProfile = "quick" | "analyze" | "review" | "free";

export type TurnProfileConfig = {
  agentRounds: number;
  reviewMode: boolean;
  singleAgent: boolean;
  consensusMode: boolean;
};

const STORAGE_KEY = "agent-lab-turn-profile";

/** Picker-visible strategies (review folded into ♾️ debate loop). */
export const TURN_STRATEGY_OPTIONS: {
  id: ComposerTurnProfile;
  label: string;
  description: string;
}[] = [
  {
    id: "quick",
    label: "빠른",
    description: "에이전트 1명 · R1 · 짧게 확인",
  },
  {
    id: "analyze",
    label: "분석",
    description: "R1 병렬 · 현황·사실·근거만 · plan 유지",
  },
  {
    id: "free",
    label: "♾️",
    description:
      "R1 주장 → R2 반박 ↔ R3 확장 루프 → 「이의 없습니다」 합의",
  },
];

export const TURN_PROFILE_OPTIONS: {
  id: ComposerTurnProfile;
  label: string;
  description: string;
}[] = [
  ...TURN_STRATEGY_OPTIONS,
  {
    id: "review",
    label: "검토",
    description: "레거시 — ♾️ 모드로 대체됨",
  },
];

export function normalizeTurnProfile(
  profile: string | null | undefined,
): ComposerTurnProfile {
  if (profile === "review") return "free";
  if (profile === "discuss") return "analyze";
  if (
    profile === "quick" ||
    profile === "analyze" ||
    profile === "free"
  ) {
    return profile;
  }
  return "analyze";
}

export function turnProfileDescription(profile: ComposerTurnProfile): string {
  const normalized = normalizeTurnProfile(profile);
  return (
    TURN_STRATEGY_OPTIONS.find((o) => o.id === normalized)?.description ??
    TURN_PROFILE_OPTIONS.find((o) => o.id === profile)?.description ??
    ""
  );
}

export const TURN_PROFILE_CONFIG: Record<ComposerTurnProfile, TurnProfileConfig> =
  {
    quick: {
      agentRounds: 1,
      reviewMode: false,
      singleAgent: true,
      consensusMode: false,
    },
    analyze: {
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
  if (stored === "efficient") {
    setEfficiencyMode(true);
    localStorage.setItem(STORAGE_KEY, "analyze");
    return "analyze";
  }
  return normalizeTurnProfile(stored);
}

export function setTurnProfile(profile: ComposerTurnProfile): void {
  localStorage.setItem(STORAGE_KEY, normalizeTurnProfile(profile));
}

export function resolveTurnSend(
  profile: ComposerTurnProfile,
  selectedAgents: string[],
  efficiencyOn = false,
): {
  agents: string[];
  agentRounds: number;
  reviewMode: boolean;
  consensusMode: boolean;
  efficiencyMode: boolean;
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
    efficiencyMode: efficiencyOn,
  };
}

export function turnProfileHint(
  profile: ComposerTurnProfile,
  selectedAgents: string[],
  efficiencyOn = false,
): string | null {
  const normalized = normalizeTurnProfile(profile);
  let hint: string | null = null;
  if (normalized === "quick" && selectedAgents.length > 1) {
    hint = `빠른 · ${selectedAgents[0]}만 · R1`;
  } else if (normalized === "free") {
    hint =
      selectedAgents.length > 1
        ? `♾️ · ${selectedAgents.length}명 · R2↔R3 루프 → 합의`
        : "♾️ · 1명 · R1";
  } else if (normalized === "analyze") {
    hint =
      selectedAgents.length > 1
        ? `분석 · ${selectedAgents.length}명 · 현황만 · R1`
        : "분석 · 현황만 · R1";
  }
  if (efficiencyOn) {
    const eff = "효율 · pin cap · 짧은 응답";
    return hint ? `${hint} · ${eff}` : eff;
  }
  return hint;
}
