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

/** Lower index = higher priority.
 *
 * Decision surfaces that unblock the current workflow come first; broader inbox
 * asks and informational surfaces follow after. This keeps the composer stack
 * aligned with "one current decision at a time".
 */
export const COMPOSER_STACK_LANE_ORDER: readonly ComposerStackLane[] = [
  "plan_approval",
  "execute_queue",
  "consensus",
  "inbox",
  "clarify",
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
      return (
        input.showClarifyNotice && !input.hasPlan && !input.planApprovalEnabled
      );
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

export type ComposerStackSnapshot = {
  pendingLanes: ComposerStackLane[];
  activeLane: ComposerStackLane | null;
  queuedLanes: ComposerStackLane[];
  pendingDecisionCount: number;
};

/** Single pass over pending lanes — prefer this when callers need more than one field. */
export function resolveComposerStackSnapshot(
  input: ComposerStackLaneInput,
): ComposerStackSnapshot {
  const pendingLanes = pendingComposerStackLanes(input);
  return {
    pendingLanes,
    activeLane: pendingLanes[0] ?? null,
    queuedLanes: pendingLanes.slice(1),
    pendingDecisionCount: pendingLanes.reduce((count, lane) => {
      if (lane === "work") return count;
      if (lane === "inbox") return count + input.inboxPendingCount;
      return count + 1;
    }, 0),
  };
}

export function resolveActiveComposerStackLane(
  input: ComposerStackLaneInput,
): ComposerStackLane | null {
  return resolveComposerStackSnapshot(input).activeLane;
}

export function pendingComposerDecisionCount(
  input: ComposerStackLaneInput,
): number {
  return resolveComposerStackSnapshot(input).pendingDecisionCount;
}
