import type {
  PlanWorkflowRecord,
  RoomObjection,
  RoomTasksPayload,
  RuntimeSnapshot,
} from "../api/client";
import {
  buildDecisionBlockedHeadline,
  type DecisionBlockedSource,
} from "./decisionBlockedHeadline";

export type InspectorTasksPrimaryAction = {
  readonly label: string;
  readonly target: "work" | "inbox" | "composer";
};

export type InspectorTasksSummaryView = {
  readonly headline: string;
  readonly detail: string;
  readonly primary: InspectorTasksPrimaryAction | null;
  readonly stats: {
    readonly openTasks: number;
    readonly openObjections: number;
    readonly inboxPending: number;
    readonly consensusBlocked: boolean;
  };
};

type BuildInput = {
  readonly locale: "ko" | "en";
  readonly roomTasks: RoomTasksPayload | null;
  readonly inboxPendingCount: number;
  readonly discussPaused: boolean;
  readonly runtime: RuntimeSnapshot | null;
  readonly showPlanApproval: boolean;
  readonly verifiedLoopPendingApproval: boolean;
  readonly firstOpenBlock: RoomObjection | null;
  readonly planWorkflow: PlanWorkflowRecord | undefined;
  readonly consensusBlocked: boolean;
  readonly workWhyBlocked?: string | null;
};

function primaryForSource(
  source: DecisionBlockedSource,
  input: BuildInput,
): InspectorTasksPrimaryAction | null {
  const ko = input.locale === "ko";
  switch (source) {
    case "inbox":
      return {
        label: ko
          ? `Composer · Inbox (${input.inboxPendingCount})`
          : `Composer · Inbox (${input.inboxPendingCount})`,
        target: "composer",
      };
    case "plan_approval":
    case "objection":
    case "plan_workflow":
      return {
        label: ko ? "Work · 승인/확인" : "Open Work",
        target: "work",
      };
    case "human_gate":
      return input.inboxPendingCount > 0
        ? {
            label: ko ? "Composer · Inbox" : "Composer · Inbox",
            target: "composer",
          }
        : {
            label: ko ? "Inbox 열기" : "Open Inbox",
            target: "inbox",
          };
    case "consensus":
      return {
        label: ko ? "Composer로 이동" : "Go to composer",
        target: "composer",
      };
    case "none":
      return null;
  }
}

export function buildInspectorTasksSummaryView(
  input: BuildInput,
): InspectorTasksSummaryView {
  const openTasks =
    (input.roomTasks?.counts?.pending ?? 0) +
    (input.roomTasks?.counts?.in_progress ?? 0);
  const openObjections = input.roomTasks?.open_objection_count ?? 0;

  const stats = {
    openTasks,
    openObjections,
    inboxPending: input.inboxPendingCount,
    consensusBlocked: input.consensusBlocked,
  };

  const blocked = buildDecisionBlockedHeadline(input);

  return {
    headline: blocked.headline,
    detail: blocked.detail,
    primary: primaryForSource(blocked.source, input),
    stats,
  };
}
