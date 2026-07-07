/**
 * Internal send config derived from room preset — not a user-facing picker.
 * Server SSOT for agent behavior: `resolve_mode_contract().runtime_turn_profile`.
 */

export type ComposerTurnProfile = "quick" | "loop";

export type TurnProfileConfig = {
  agentRounds: number;
  reviewMode: boolean;
  singleAgent: boolean;
  consensusMode: boolean;
};

const PROFILE_CONFIG: Record<ComposerTurnProfile, TurnProfileConfig> = {
  quick: {
    agentRounds: 1,
    reviewMode: false,
    singleAgent: true,
    consensusMode: false,
  },
  loop: {
    agentRounds: 1,
    reviewMode: false,
    singleAgent: false,
    consensusMode: false,
  },
};

/** Map room_preset → client send roster config (fast/supervisor only). */
export function turnProfileForRoomPreset(
  presetId: string | null | undefined,
): ComposerTurnProfile {
  if (presetId === "fast") return "quick";
  return "loop";
}

/** Legacy API / SSE aliases → client send profile. */
export function normalizeTurnProfile(
  profile: string | null | undefined,
): ComposerTurnProfile {
  if (profile === "quick" || profile === "fast") return "quick";
  return "loop";
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
  const cfg = PROFILE_CONFIG[profile];
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
