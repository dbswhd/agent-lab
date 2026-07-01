/** Composer stack — one blocking surface at a time (precedence = product SSOT). */

export type ComposerStackLane =
  | "inbox"
  | "plan_approval"
  | "clarify"
  | "execute_queue"
  | "consensus"
  | "work";

export type ComposerStackLaneInput = {
  inboxPendingCount: number;
  planApprovalEnabled: boolean;
  showClarifyNotice: boolean;
  hasPlan: boolean;
  showExecuteQueue: boolean;
  execPending: boolean;
  showConsensusGate: boolean;
  consensusProposal: unknown;
  showWorkSurface: boolean;
};

/** Lower index = higher priority. Matches backend gates (inbox before build GO). */
export const COMPOSER_STACK_LANE_ORDER: readonly ComposerStackLane[] = [
  "inbox",
  "plan_approval",
  "clarify",
  "execute_queue",
  "consensus",
  "work",
] as const;

function laneReady(
  lane: ComposerStackLane,
  input: ComposerStackLaneInput,
): boolean {
  switch (lane) {
    case "inbox":
      return input.inboxPendingCount > 0;
    case "plan_approval":
      return input.planApprovalEnabled;
    case "clarify":
      return input.showClarifyNotice && !input.hasPlan && !input.planApprovalEnabled;
    case "execute_queue":
      return input.showExecuteQueue && input.execPending;
    case "consensus":
      return input.showConsensusGate && Boolean(input.consensusProposal);
    case "work":
      return input.showWorkSurface && !input.planApprovalEnabled;
    default:
      return false;
  }
}

export function pendingComposerStackLanes(
  input: ComposerStackLaneInput,
): ComposerStackLane[] {
  return COMPOSER_STACK_LANE_ORDER.filter((lane) => laneReady(lane, input));
}

export function resolveActiveComposerStackLane(
  input: ComposerStackLaneInput,
): ComposerStackLane | null {
  return pendingComposerStackLanes(input)[0] ?? null;
}
