import type {
  WorkDecisionActionId,
  WorkDecisionCellState,
  WorkDecisionPanelCell,
  WorkDecisionSummary,
} from "./workDecisionTypes";

type SummaryDraft = Omit<WorkDecisionSummary, "cells"> & {
  readonly approve: readonly [string, string, WorkDecisionCellState];
  readonly blocked: readonly [string, string, WorkDecisionCellState];
  readonly verified: readonly [string, string, WorkDecisionCellState];
};

function cell(
  label: WorkDecisionPanelCell["label"],
  row: readonly [string, string, WorkDecisionCellState],
): WorkDecisionPanelCell {
  return { label, value: row[0], detail: row[1], state: row[2] };
}

export function workDecisionSummary(
  draft: SummaryDraft,
): WorkDecisionSummary {
  return {
    kind: draft.kind,
    eyebrow: draft.eyebrow,
    title: draft.title,
    detail: draft.detail,
    whatToApprove: draft.whatToApprove,
    whyBlocked: draft.whyBlocked,
    verificationStatus: draft.verificationStatus,
    primaryTarget: draft.primaryTarget,
    primaryLabel: draft.primaryLabel,
    secondaryTarget: draft.secondaryTarget,
    secondaryLabel: draft.secondaryLabel,
    cells: [
      cell("Approve", draft.approve),
      cell("Blocked", draft.blocked),
      cell("Verified", draft.verified),
    ],
  };
}

export function blockedWorkDecision(input: {
  readonly eyebrow: string;
  readonly title: string;
  readonly detail: string;
  readonly approve?: string;
  readonly verified?: string;
  readonly primaryTarget?: WorkDecisionActionId;
  readonly primaryLabel?: string;
  readonly secondaryTarget?: WorkDecisionActionId;
  readonly secondaryLabel?: string;
}): WorkDecisionSummary {
  return workDecisionSummary({
    kind: "blocked",
    eyebrow: input.eyebrow,
    title: input.title,
    detail: input.detail,
    whatToApprove: input.approve ?? "차단 해소 전 승인 금지",
    whyBlocked: input.detail,
    verificationStatus: input.verified ?? "검증 대기",
    primaryTarget: input.primaryTarget ?? "focus_checks",
    primaryLabel: input.primaryLabel ?? "차단 근거 보기",
    secondaryTarget: input.secondaryTarget,
    secondaryLabel: input.secondaryLabel,
    approve: ["보류", input.approve ?? "실패를 먼저 해소하세요.", "blocked"],
    blocked: ["차단됨", input.detail, "blocked"],
    verified: [input.verified ?? "대기", "완료로 볼 수 없습니다.", "blocked"],
  });
}
