import type { RuntimeSnapshot } from "../api/client";

export type HumanDecisionLaneId = "discuss" | "plan" | "execute";

export type HumanDecisionLane = {
  id: HumanDecisionLaneId;
  blocked: boolean;
  reason?: string | null;
};

export function buildHumanDecisionLanes(
  runtime: RuntimeSnapshot | null,
  discussPaused: boolean,
): HumanDecisionLane[] {
  const gates = runtime?.gates;
  // A fresh runtime snapshot confirming the gate is open wins over the
  // client-only `discussPaused` flag — that flag only flips back to false
  // when *this* tab is the one that resolves the inbox item (see
  // useRoomChatInteractions.handleInboxResolved), so another tab/session
  // resolving it would otherwise leave this tab's banner stuck forever.
  const discussGateOpen = gates?.discuss?.open;
  const discussBlocked =
    discussGateOpen === true
      ? false
      : discussPaused || discussGateOpen === false;
  return [
    {
      id: "discuss",
      blocked: discussBlocked,
      reason: discussBlocked
        ? (gates?.discuss?.reason ??
          (discussPaused ? "pending_question" : null))
        : null,
    },
    {
      id: "plan",
      blocked: gates?.plan_clarify?.open === false,
      reason: gates?.plan_clarify?.reason ?? null,
    },
    {
      id: "execute",
      blocked: gates?.execute?.open === false,
      reason: gates?.execute?.reason ?? gates?.block_reason ?? null,
    },
  ];
}

/** Show unified banner when Human Inbox gates any lane (not generic execute/objection blocks). */
export function shouldShowHumanDecisionBanner(
  runtime: RuntimeSnapshot | null,
  discussPaused: boolean,
): boolean {
  const lanes = buildHumanDecisionLanes(runtime, discussPaused);
  const inboxPending =
    discussPaused || (runtime?.inbox?.pending_count ?? 0) > 0;
  if (lanes.find((l) => l.id === "discuss")?.blocked) return true;
  if (lanes.find((l) => l.id === "plan")?.blocked) return true;
  if (inboxPending && lanes.find((l) => l.id === "execute")?.blocked) {
    return true;
  }
  return false;
}

export function humanDecisionBlockedLanes(
  lanes: HumanDecisionLane[],
): HumanDecisionLane[] {
  return lanes.filter((lane) => lane.blocked);
}
