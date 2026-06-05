import {
  normalizeTurnProfile,
  resolveTurnSend,
  type ComposerTurnProfile,
} from "./turnProfile";

export type TurnCostEstimate = {
  agentCount: number;
  parallelRounds: number;
  estimatedAgentCalls: number;
  label: string;
  /** Short suffix for inline composer hint (one line with mode description). */
  compactLabel: string;
  isFullTeam: boolean;
  requiresConfirm: boolean;
};

type EstimateOptions = {
  efficiencyOn?: boolean;
};

// Keep these aligned with backend defaults:
// src/agent_lab/room.py DEFAULT_AGENT_PARALLEL_ROUNDS / MAX_AGENT_PARALLEL_ROUNDS
// src/agent_lab/room_consensus.py DEFAULT_MAX_CONSENSUS_ROUNDS / CALLS
// src/agent_lab/context_limits.py efficiency consensus defaults.
const DEFAULT_AGENT_PARALLEL_ROUNDS = 1;
const MAX_AGENT_PARALLEL_ROUNDS = 4;
const DEFAULT_MAX_CONSENSUS_ROUNDS = 12;
const DEFAULT_MAX_CONSENSUS_CALLS = 30;
const EFFICIENCY_MAX_CONSENSUS_ROUNDS = 8;
const EFFICIENCY_MAX_CONSENSUS_CALLS = 20;

function clampRounds(rounds: number): number {
  return Math.max(
    DEFAULT_AGENT_PARALLEL_ROUNDS,
    Math.min(rounds, MAX_AGENT_PARALLEL_ROUNDS),
  );
}

function callSuffix(calls: number, max = false): string {
  return `${max ? "최대 " : ""}~${calls}회`;
}

export function estimateTurnCost(
  profile: ComposerTurnProfile,
  selectedAgents: string[],
  opts: EstimateOptions = {},
): TurnCostEstimate {
  const normalized = normalizeTurnProfile(profile);
  const resolved = resolveTurnSend(normalized, selectedAgents, opts.efficiencyOn);
  const agentCount = resolved.agents.length;
  const selectedCount = selectedAgents.length;
  const consensusMaxCalls = opts.efficiencyOn
    ? EFFICIENCY_MAX_CONSENSUS_CALLS
    : DEFAULT_MAX_CONSENSUS_CALLS;
  const consensusMaxRounds = opts.efficiencyOn
    ? EFFICIENCY_MAX_CONSENSUS_ROUNDS
    : DEFAULT_MAX_CONSENSUS_ROUNDS;

  let estimatedAgentCalls = agentCount;
  let parallelRounds = clampRounds(resolved.agentRounds);
  let maxLabel = false;
  let modeLabel = "분석";

  if (normalized === "quick") {
    estimatedAgentCalls = agentCount > 0 ? 1 : 0;
    parallelRounds = 1;
    modeLabel = "빠른";
  } else if (normalized === "specialist") {
    parallelRounds = 2;
    estimatedAgentCalls =
      agentCount >= 3 ? 3 : agentCount === 1 ? 2 : Math.max(2, agentCount);
    modeLabel = "분업";
  } else if (normalized === "free") {
    parallelRounds = consensusMaxRounds;
    estimatedAgentCalls = agentCount > 0 ? consensusMaxCalls : 0;
    maxLabel = true;
    modeLabel = "♾️ 합의";
  } else {
    estimatedAgentCalls = agentCount;
    parallelRounds = 1;
  }

  const isFullTeam =
    selectedCount >= 3 &&
    (normalized === "free" ||
      normalized === "specialist" ||
      (agentCount >= 3 && parallelRounds >= 2));
  const requiresConfirm = isFullTeam;
  const roundLabel =
    normalized === "free" ? `최대 ${parallelRounds}R` : `${parallelRounds}R`;
  const label = `예상 에이전트 호출 ${callSuffix(
    estimatedAgentCalls,
    maxLabel,
  )} (${modeLabel} · ${agentCount}명 · ${roundLabel})`;
  const compactLabel = `예상 ${callSuffix(estimatedAgentCalls, maxLabel)}`;

  return {
    agentCount,
    parallelRounds,
    estimatedAgentCalls,
    label,
    compactLabel,
    isFullTeam,
    requiresConfirm,
  };
}
