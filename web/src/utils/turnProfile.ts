import { setEfficiencyMode } from "./efficiencyPrefs";

export type ComposerTurnProfile =
  | "quick"
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

/** Picker-visible strategies (review folded into ♾️ debate loop). */
export function turnStrategyOptions(locale: "en" | "ko" = "en") {
  const ko = locale === "ko";
  return [
    {
      id: "quick" as const,
      label: ko ? "빠른" : "Quick",
      description: ko ? "에이전트 1명 · R1 · 짧게 확인" : "1 agent · R1 · short check",
    },
    {
      id: "analyze" as const,
      label: ko ? "분석" : "Analyze",
      description: ko
        ? "R1 병렬 · 현황·사실만 · plan 유지"
        : "R1 parallel · facts only · keep plan",
    },
    {
      id: "specialist" as const,
      label: ko ? "분업" : "Split",
      description: "R1 Codex+Claude → R2 Cursor",
    },
    {
      id: "free" as const,
      label: "♾️",
      description: ko
        ? "R1 주장 → R2 반박 ↔ R3 확장 루프 → 합의"
        : "Claim → rebuttal ↔ expand loop → consensus",
    },
  ];
}

/** @deprecated use turnStrategyOptions(locale) */
export const TURN_STRATEGY_OPTIONS = turnStrategyOptions("en");

/** One-line hint under turn picker — matches offline prototype composer.jsx */
export function composerTurnHint(
  profile: ComposerTurnProfile,
  selectedAgents: string[],
  efficiencyOn = false,
  locale: "en" | "ko" = "en",
): string {
  const normalized = normalizeTurnProfile(profile);
  const resolved = resolveTurnSend(normalized, selectedAgents, efficiencyOn);
  const n = resolved.agents.length;
  const ko = locale === "ko";
  if (normalized === "quick") {
    const lead = selectedAgents[0] ?? "agent";
    return ko
      ? n > 1
        ? `빠른 · ${lead}만 · R1`
        : "빠른 · R1"
      : n > 1
        ? `Quick · ${lead} only · R1`
        : "Quick · R1";
  }
  if (normalized === "analyze") {
    return ko
      ? `분석 · ${n}명 · 현황·사실만 · R${resolved.agentRounds}`
      : `Analyze · ${n} agents · facts only · R${resolved.agentRounds}`;
  }
  if (normalized === "specialist") {
    return ko
      ? "분업 · R1 Codex+Claude → R2 Cursor"
      : "Split · R1 Codex+Claude → R2 Cursor";
  }
  if (normalized === "verified") {
    return ko
      ? "검증 · 목표 합의 → Oracle VERIFIED"
      : "Verified · goal → Oracle VERIFIED";
  }
  if (normalized === "free") {
    return ko
      ? `♾️ · ${n}명 · R2↔R3 루프 → 합의`
      : `♾️ · ${n} agents · R2↔R3 loop → consensus`;
  }
  return turnProfileDescription(profile);
}

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
  if (profile === "verified") return "analyze";
  if (
    profile === "quick" ||
    profile === "analyze" ||
    profile === "free" ||
    profile === "specialist"
  ) {
    return profile;
  }
  return "analyze";
}

export function turnProfileDescription(profile: ComposerTurnProfile): string {
  const normalized = normalizeTurnProfile(profile);
  return (
    turnStrategyOptions("en").find((o) => o.id === normalized)?.description ??
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
  if (stored === "efficient") {
    setEfficiencyMode(true);
    localStorage.setItem(STORAGE_KEY, "analyze");
    return "analyze";
  }
  if (stored === "verified") {
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
  } else if (normalized === "specialist") {
    hint =
      selectedAgents.length > 1
        ? `분업 · R1 Codex+Claude → R2 Cursor`
        : "분업 · 2R · Cursor R2";
  } else if (normalized === "verified") {
    hint =
      selectedAgents.length > 1
        ? `검증 · ${selectedAgents.length}명 · Oracle VERIFIED`
        : "검증 · Oracle VERIFIED";
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
