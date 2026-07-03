import type { LiveMsg } from "../run/runSessionRegistry";
import { agentLabel, isReplyWaitRole, type AgentRole } from "../utils/transcript";

export type RunningAgentSlot = {
  agent: string;
  round: number;
  label: string;
  activity?: string;
};

export type PendingReplyAgent = {
  id: string;
  role: AgentRole;
  label: string;
};

/** Agents still expected to reply before the first typing bubble arrives. */
function pendingAgentsForExpected(
  expectedAgents: string[],
  topologyDone: Set<string>,
  round = 1,
): PendingReplyAgent[] {
  return expectedAgents
    .filter((id) => !topologyDone.has(`${id}:${round}`))
    .map((id) => ({
      id: `pending-${id}-r${round}`,
      role: id as AgentRole,
      label: agentLabel(id),
    }));
}

export function derivePendingReplyAgents(
  messages: LiveMsg[],
  options: {
    running: boolean;
    expectedAgents: string[];
    /** True when the user @-mentioned a subset (not the full roster). */
    mentionFiltered?: boolean;
    topologyActive: { agent: string; round: number } | null;
    topologyDone: Set<string>;
  },
): PendingReplyAgent[] {
  if (!options.running) return [];
  const typing = messages.filter((m) => m.typing && isReplyWaitRole(m.role));
  if (typing.length > 0) return [];

  const { topologyActive, topologyDone, expectedAgents } = options;
  if (topologyActive) {
    const { agent, round } = topologyActive;
    if (topologyDone.has(`${agent}:${round}`)) return [];
    return [
      {
        id: `pending-${agent}-r${round}`,
        role: agent as AgentRole,
        label: agentLabel(agent),
      },
    ];
  }

  // Before the first agent_start SSE, avoid roster-wide placeholders — but
  // @-mention filtered turns should show the targeted agent(s) only (§5.3).
  if (topologyDone.size === 0) {
    if (options.mentionFiltered && expectedAgents.length > 0) {
      return pendingAgentsForExpected(expectedAgents, topologyDone);
    }
    return [];
  }

  return pendingAgentsForExpected(expectedAgents, topologyDone);
}

/** Live slots from typing bubbles; fallback to expected agents before first SSE. */
export function deriveRunningAgentSlots(
  messages: LiveMsg[],
  options: { running: boolean; expectedAgents: string[] },
): RunningAgentSlot[] {
  const { running, expectedAgents } = options;
  const typing = messages.filter((m) => m.typing && isReplyWaitRole(m.role));
  if (typing.length) {
    return typing.map((m) => ({
      agent: String(m.role),
      round: m.parallelRound ?? 1,
      label: m.label || agentLabel(String(m.role)),
      activity: [...(m.turnItems ?? [])]
        .reverse()
        .flatMap((item) =>
          item.kind === "activity" || item.kind === "reasoning_summary"
            ? [item.text]
            : [],
        )[0],
    }));
  }
  return [];
}

export function runningAgentsSummary(
  slots: RunningAgentSlot[],
  locale: "en" | "ko" = "ko",
): string | null {
  if (!slots.length) return null;
  const names = slots.map((s) => s.label).join(", ");
  if (locale === "ko") {
    return slots.length === 1
      ? `${names} 실행 중`
      : `${names} 실행 중 (${slots.length})`;
  }
  return slots.length === 1
    ? `${names} running`
    : `${names} running (${slots.length})`;
}

export function pickPrimaryRunningSlot(
  slots: RunningAgentSlot[],
): RunningAgentSlot | null {
  return slots[0] ?? null;
}
