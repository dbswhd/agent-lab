import type { LiveMsg } from "./runSessionRegistry";
import { agentLabel, isReplyWaitRole } from "../utils/transcript";

export type RunningAgentSlot = {
  agent: string;
  round: number;
  label: string;
  activities?: string[];
};

/** Live slots from typing bubbles; fallback to expected agents before first SSE. */
export function deriveRunningAgentSlots(
  messages: LiveMsg[],
  options: { running: boolean; expectedAgents: string[] },
): RunningAgentSlot[] {
  const { running, expectedAgents } = options;
  const typing = messages.filter(
    (m) => m.typing && isReplyWaitRole(m.role),
  );
  if (typing.length) {
    return typing.map((m) => ({
      agent: String(m.role),
      round: m.parallelRound ?? 1,
      label: m.label || agentLabel(String(m.role)),
      activities: m.activities,
    }));
  }
  if (running && expectedAgents.length) {
    return expectedAgents.map((id) => ({
      agent: id,
      round: 1,
      label: agentLabel(id),
      activities: [],
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
  return slots.length === 1 ? `${names} running` : `${names} running (${slots.length})`;
}

export function pickPrimaryRunningSlot(
  slots: RunningAgentSlot[],
): RunningAgentSlot | null {
  return slots[0] ?? null;
}
