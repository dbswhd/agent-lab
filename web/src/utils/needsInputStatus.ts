import type {
  PlanWorkflowRecord,
  RuntimeSnapshot,
} from "../api/client";
import type { ComposerStackLane } from "./composerStackLane";
import {
  buildHumanDecisionLanes,
  humanDecisionBlockedLanes,
} from "./humanDecisionView";

export type NeedsInputReason =
  | "plan_approval"
  | "execute_approval"
  | "inbox_question"
  | "inbox_build"
  | "inbox_autonomy"
  | "inbox"
  | "human_gate"
  | "none";

export type NeedsInputStatus = {
  active: boolean;
  label: string;
  detail: string;
  count: number;
  primaryReason: NeedsInputReason;
  focus: ComposerStackLane | "inbox";
};

export type NeedsInputBuildInput = {
  locale: "ko" | "en";
  inboxPendingCount: number;
  inboxPendingQuestions: number;
  inboxPendingBuilds: number;
  inboxPendingAutonomy?: number;
  showPlanApproval: boolean;
  verifiedLoopPendingApproval: boolean;
  execPendingApproval: boolean;
  discussPaused: boolean;
  runtime: RuntimeSnapshot | null;
  planWorkflow?: PlanWorkflowRecord;
};

/** Codex/CC-style "Needs input" aggregator — mirrors composer stack precedence. */
export function buildNeedsInputStatus(
  input: NeedsInputBuildInput,
): NeedsInputStatus {
  const ko = input.locale === "ko";
  const idle: NeedsInputStatus = {
    active: false,
    label: ko ? "입력 필요 없음" : "No input needed",
    detail: "",
    count: 0,
    primaryReason: "none",
    focus: "inbox",
  };

  if (input.showPlanApproval || input.verifiedLoopPendingApproval) {
    return {
      active: true,
      label: ko ? "입력 필요" : "Needs input",
      detail: ko ? "Plan 승인 대기" : "Plan approval pending",
      count: 1,
      primaryReason: "plan_approval",
      focus: "plan_approval",
    };
  }

  if (input.execPendingApproval) {
    return {
      active: true,
      label: ko ? "입력 필요" : "Needs input",
      detail: ko ? "Execute / merge 승인 대기" : "Execute approval pending",
      count: 1,
      primaryReason: "execute_approval",
      focus: "execute_queue",
    };
  }

  if (input.inboxPendingQuestions > 0 || input.discussPaused) {
    const n = Math.max(input.inboxPendingQuestions, input.discussPaused ? 1 : 0);
    return {
      active: true,
      label: ko ? "입력 필요" : "Needs input",
      detail: ko ? `질문 ${n}건` : `${n} question(s)`,
      count: n,
      primaryReason: "inbox_question",
      focus: "inbox",
    };
  }

  const autonomy = input.inboxPendingAutonomy ?? 0;
  if (autonomy > 0) {
    return {
      active: true,
      label: ko ? "입력 필요" : "Needs input",
      detail: ko ? "Autonomy 확인" : "Autonomy confirmation",
      count: autonomy,
      primaryReason: "inbox_autonomy",
      focus: "inbox",
    };
  }

  if (input.inboxPendingBuilds > 0) {
    return {
      active: true,
      label: ko ? "입력 필요" : "Needs input",
      detail: ko
        ? `Build 확인 ${input.inboxPendingBuilds}건`
        : `${input.inboxPendingBuilds} build confirmation(s)`,
      count: input.inboxPendingBuilds,
      primaryReason: "inbox_build",
      focus: "inbox",
    };
  }

  if (input.inboxPendingCount > 0) {
    return {
      active: true,
      label: ko ? "입력 필요" : "Needs input",
      detail: ko
        ? `Inbox ${input.inboxPendingCount}건`
        : `${input.inboxPendingCount} inbox item(s)`,
      count: input.inboxPendingCount,
      primaryReason: "inbox",
      focus: "inbox",
    };
  }

  const lanes = humanDecisionBlockedLanes(
    buildHumanDecisionLanes(input.runtime, input.discussPaused),
  );
  if (lanes.length > 0) {
    return {
      active: true,
      label: ko ? "입력 필요" : "Needs input",
      detail: ko ? "Human gate 차단" : "Human gate blocked",
      count: lanes.length,
      primaryReason: "human_gate",
      focus: "inbox",
    };
  }

  return idle;
}
