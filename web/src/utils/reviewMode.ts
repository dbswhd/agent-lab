import { agentLabel } from "./transcript";

/** Matches server `_review_advocate` rotation (index before current send). */
export function pickReviewAdvocate(
  agents: string[],
  humanTurnIndex: number,
): string | null {
  if (agents.length === 0) return null;
  return agents[humanTurnIndex % agents.length];
}

export function countUserTurns(messages: { role: string }[]): number {
  return messages.filter((m) => m.role === "you").length;
}

export function reviewAdvocateLabel(
  agents: string[],
  humanTurnIndex: number,
): string | null {
  const id = pickReviewAdvocate(agents, humanTurnIndex);
  return id ? agentLabel(id) : null;
}
