import { setEfficiencyMode } from "./efficiencyPrefs";

export type ComposerTurnProfile = "quick" | "discuss" | "review" | "free";

export type TurnProfileConfig = {
  agentRounds: number;
  reviewMode: boolean;
  singleAgent: boolean;
  consensusMode: boolean;
};

const STORAGE_KEY = "agent-lab-turn-profile";

export const TURN_PROFILE_OPTIONS: {
  id: ComposerTurnProfile;
  label: string;
  description: string;
}[] = [
  {
    id: "quick",
    label: "빠른",
    description: "에이전트 1명 · 1라운드 · 짧게 확인",
  },
  {
    id: "discuss",
    label: "회의",
    description: "선택 에이전트 · R1 병렬 → R2 순차 · plan은 그대로",
  },
  {
    id: "review",
    label: "논쟁",
    description: "R1 병렬 → R2 순차 (claude→codex→cursor) · 쟁점 집중",
  },
  {
    id: "free",
    label: "♾️",
    description: "R1 병렬 후 「이의 없습니다」까지 순차 (최대 12라운드)",
  },
];

export function turnProfileDescription(profile: ComposerTurnProfile): string {
  return (
    TURN_PROFILE_OPTIONS.find((o) => o.id === profile)?.description ?? ""
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
    discuss: {
      agentRounds: 2,
      reviewMode: false,
      singleAgent: false,
      consensusMode: false,
    },
    review: {
      agentRounds: 2,
      reviewMode: true,
      singleAgent: false,
      consensusMode: false,
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
    localStorage.setItem(STORAGE_KEY, "discuss");
    return "discuss";
  }
  if (
    stored === "quick" ||
    stored === "discuss" ||
    stored === "review" ||
    stored === "free"
  ) {
    return stored;
  }
  return "discuss";
}

export function setTurnProfile(profile: ComposerTurnProfile): void {
  localStorage.setItem(STORAGE_KEY, profile);
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
  const cfg = TURN_PROFILE_CONFIG[profile];
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
  let hint: string | null = null;
  if (profile === "quick" && selectedAgents.length > 1) {
    hint = `빠른 · ${selectedAgents[0]}만 · 1라운드`;
  } else if (profile === "free") {
    hint =
      selectedAgents.length > 1
        ? `♾️ · ${selectedAgents.length}명 · 「이의 없습니다」까지`
        : "♾️ · 1명 · 1라운드";
  } else if (profile === "review") {
    hint = "논쟁 · R1 병렬 → R2 · claude→codex→cursor";
  } else if (profile === "discuss") {
    hint =
      selectedAgents.length > 1
        ? `회의 · ${selectedAgents.length}명 · R1 병렬 → R2 순차`
        : "회의 · R1 병렬 → R2 순차";
  }
  if (efficiencyOn) {
    const eff = "효율 · pin cap · 짧은 응답";
    return hint ? `${hint} · ${eff}` : eff;
  }
  return hint;
}
