import type {
  PlanWorkflowRecord,
  RoomObjection,
  RuntimeSnapshot,
} from "../api/client";
import {
  buildHumanDecisionLanes,
  humanDecisionBlockedLanes,
  type HumanDecisionLaneId,
} from "./humanDecisionView";

export type DecisionBlockedSource =
  | "inbox"
  | "plan_approval"
  | "human_gate"
  | "objection"
  | "consensus"
  | "plan_workflow"
  | "none";

export type DecisionBlockedHeadline = {
  readonly headline: string;
  readonly detail: string;
  readonly source: DecisionBlockedSource;
};

type BuildInput = {
  readonly locale: "ko" | "en";
  readonly inboxPendingCount: number;
  readonly discussPaused: boolean;
  readonly runtime: RuntimeSnapshot | null;
  readonly showPlanApproval: boolean;
  readonly verifiedLoopPendingApproval: boolean;
  readonly firstOpenBlock: RoomObjection | null;
  readonly consensusBlocked: boolean;
  readonly planWorkflow: PlanWorkflowRecord | undefined;
  readonly workWhyBlocked?: string | null;
};

const LANE_PRIORITY: readonly HumanDecisionLaneId[] = [
  "discuss",
  "plan",
  "execute",
];

function humanizeReason(reason: string, ko: boolean): string {
  const normalized = reason.replace(/_/g, " ").trim();
  if (!normalized) return ko ? "게이트 차단" : "Gate blocked";
  return normalized;
}

function laneLabel(id: HumanDecisionLaneId, ko: boolean): string {
  switch (id) {
    case "discuss":
      return ko ? "Discuss" : "Discuss";
    case "plan":
      return ko ? "Plan clarify" : "Plan clarify";
    case "execute":
      return ko ? "Execute" : "Execute";
  }
}

function humanGateHeadline(
  runtime: RuntimeSnapshot | null,
  discussPaused: boolean,
  ko: boolean,
): DecisionBlockedHeadline | null {
  const lanes = humanDecisionBlockedLanes(
    buildHumanDecisionLanes(runtime, discussPaused),
  );
  if (lanes.length === 0) return null;
  const lane =
    LANE_PRIORITY.map((id) => lanes.find((row) => row.id === id)).find(
      Boolean,
    ) ?? lanes[0];
  const reason = humanizeReason(
    lane.reason ?? (discussPaused ? "pending_question" : "blocked"),
    ko,
  );
  return {
    source: "human_gate",
    headline: ko
      ? `${laneLabel(lane.id, ko)} 차단: ${reason}`
      : `${laneLabel(lane.id, ko)} blocked: ${reason}`,
    detail: ko
      ? "Human Inbox에서 결정하면 다음 단계로 진행됩니다."
      : "Resolve the Human Inbox item to continue.",
  };
}

/** Single-line blocked/pending headline SSOT for composer, tasks, and banners. */
export function buildDecisionBlockedHeadline(
  input: BuildInput,
): DecisionBlockedHeadline {
  const ko = input.locale === "ko";

  if (input.inboxPendingCount > 0) {
    return {
      source: "inbox",
      headline: ko
        ? `Human Inbox ${input.inboxPendingCount}건 대기`
        : `${input.inboxPendingCount} Human Inbox pending`,
      detail: ko
        ? "질문·실행 확인은 Composer에서 처리하세요."
        : "Answer in the composer.",
    };
  }

  if (input.showPlanApproval || input.verifiedLoopPendingApproval) {
    return {
      source: "plan_approval",
      headline: ko ? "Plan 승인 대기" : "Plan approval pending",
      detail: ko
        ? "승인·execute 판단은 composer stack에서만 처리합니다."
        : "Review and approve in the composer stack only.",
    };
  }

  const gate = humanGateHeadline(input.runtime, input.discussPaused, ko);
  if (gate) return gate;

  if (input.firstOpenBlock) {
    return {
      source: "objection",
      headline: ko ? "BLOCK 이의 미해결" : "Open BLOCK objection",
      detail: input.firstOpenBlock.body,
    };
  }

  if (input.consensusBlocked) {
    return {
      source: "consensus",
      headline: ko ? "팀 합의 대기" : "Team consensus pending",
      detail: ko
        ? "Composer 아래 Task bar에서 동의·완료를 처리하세요."
        : "Use the composer task bar to endorse or complete.",
    };
  }

  if (input.workWhyBlocked?.trim()) {
    return {
      source: "human_gate",
      headline: ko ? "Execute 차단" : "Execute blocked",
      detail: input.workWhyBlocked.trim(),
    };
  }

  const phase = (input.planWorkflow?.phase ?? "").toUpperCase();
  if (phase && phase !== "APPROVED" && phase !== "IDLE") {
    const clarify = phase === "CLARIFY";
    return {
      source: "plan_workflow",
      headline: ko ? `Plan workflow · ${phase}` : `Plan workflow · ${phase}`,
      detail: clarify
        ? ko
          ? "Clarify 질문·답변은 Composer Human Inbox 또는 stack · Clarify에서 확인하세요."
          : "Track clarify Q&A in the composer Human Inbox or stack · Clarify."
        : ko
          ? "진행 상태는 Composer stack에서 확인하세요."
          : "Track progress in the composer stack.",
    };
  }

  return {
    source: "none",
    headline: ko ? "지금 Human 결정 없음" : "No Human decision pending",
    detail: ko
      ? "열린 작업·이의는 Composer 아래 Task bar에서 처리합니다."
      : "Open tasks live in the composer task bar.",
  };
}
