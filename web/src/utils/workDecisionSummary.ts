import type {
  MergeChecksPayload,
  PlanExecutionRecord,
  PlanWorkflowRecord,
  RoomTasksPayload,
  RuntimeSnapshot,
} from "../api/client";
import type { PlanMetaView } from "./planMeta";
import { findActiveExecution } from "./planExecuteWorktree";
import type { VerifiedLoopView } from "./verifiedLoopView";
import {
  blockedWorkDecision,
  workDecisionSummary,
} from "./workDecisionSummaryView";
import type { WorkDecisionSummary } from "./workDecisionTypes";
export type {
  WorkDecisionActionId,
  WorkDecisionSummary,
} from "./workDecisionTypes";

type WorkDecisionInput = {
  readonly hasPlan: boolean;
  readonly planMeta: PlanMetaView;
  readonly planStaleNotice?: string | null;
  readonly planWorkflow?: PlanWorkflowRecord;
  readonly verifiedLoopView: VerifiedLoopView;
  readonly runtime?: RuntimeSnapshot | null;
  readonly executions: readonly PlanExecutionRecord[];
  readonly mergeChecks?: MergeChecksPayload | null;
  readonly workHookAlert?: {
    readonly body: string;
    readonly blocked: boolean;
  } | null;
  readonly roomTasks?: RoomTasksPayload | null;
};

const PASS_STATUSES = new Set(["pass", "passed"]);
const FAIL_STATUSES = new Set(["fail", "failed"]);

function latestExecution(
  executions: readonly PlanExecutionRecord[],
): PlanExecutionRecord | null {
  for (let i = executions.length - 1; i >= 0; i -= 1) {
    const row = executions[i];
    if (row) return row;
  }
  return null;
}

function oracleStatus(row: PlanExecutionRecord | null): string | null {
  return (
    row?.verify_after_merge?.status ??
    row?.verify_after_merge?.oracle?.verdict ??
    row?.oracle?.verdict ??
    row?.oracle_verdict ??
    null
  );
}

function planApprovalPending(input: WorkDecisionInput): boolean {
  const phase = (input.planWorkflow?.phase ?? "").toUpperCase();
  return (
    Boolean(input.planWorkflow?.enabled) &&
    (phase === "HUMAN_PENDING" || input.verifiedLoopView.pendingApproval)
  );
}

function openBlockReason(input: WorkDecisionInput): string | null {
  const block = input.roomTasks?.open_objections?.find(
    (row) => row.act === "BLOCK" && row.status === "open",
  );
  return block ? `${block.from}: ${block.body}` : null;
}

export function buildWorkDecisionSummary(
  input: WorkDecisionInput,
): WorkDecisionSummary {
  const executions = [...input.executions];
  const active = findActiveExecution(executions);
  const latest = latestExecution(executions);
  const status = oracleStatus(active ?? latest);
  const oracleFailed = status ? FAIL_STATUSES.has(status) : false;
  const oraclePassed = status ? PASS_STATUSES.has(status) : false;
  const runtimeBlock =
    input.runtime?.gates.block_reason ??
    input.runtime?.gates.execute?.reason ??
    input.runtime?.last_failure?.reason ??
    null;
  const blockReason = openBlockReason(input);

  if (!input.hasPlan) {
    return workDecisionSummary({
      kind: "plan_needed",
      eyebrow: "Work",
      title: "plan.md가 필요합니다",
      detail: "토론을 정리한 뒤 승인과 execute 판단을 시작할 수 있습니다.",
      whatToApprove: "승인할 plan 없음",
      whyBlocked: "plan.md 없음",
      verificationStatus: "검증 전",
      primaryTarget: "focus_plan",
      primaryLabel: "Plan 위치 보기",
      approve: ["대기 없음", "먼저 plan.md를 만드세요.", "idle"],
      blocked: ["Plan 필요", "execute gate가 열리지 않았습니다.", "blocked"],
      verified: ["검증 전", "Oracle 결과가 없습니다.", "idle"],
    });
  }

  if (input.planStaleNotice || input.planMeta.pendingAgreement) {
    const reason = input.planStaleNotice ?? input.planMeta.freshnessLabel;
    return blockedWorkDecision({
      eyebrow: "Work blocked",
      title: "plan.md 동기화가 필요합니다",
      detail: reason,
      approve: "동기화 전 승인 금지",
      verified: "검증 전",
      primaryTarget: "focus_plan",
      primaryLabel: "Plan 갱신 위치 보기",
    });
  }

  if (input.workHookAlert?.blocked || blockReason || runtimeBlock) {
    const reason =
      input.workHookAlert?.body ?? blockReason ?? runtimeBlock ?? "";
    return blockedWorkDecision({
      eyebrow: "Work blocked",
      title: "execute gate가 막혔습니다",
      detail: reason,
      verified: oraclePassed ? "Oracle PASS 기록 있음" : "검증 대기",
      secondaryTarget: "open_tasks",
      secondaryLabel: "Tasks 보기",
    });
  }

  if (active?.status === "merge_conflict") {
    return blockedWorkDecision({
      eyebrow: "Merge blocked",
      title: "merge 충돌을 해결해야 합니다",
      detail: "main 병합 중 충돌",
      approve: "Conflict 해결 완료 또는 Merge 취소",
      verified: "검증 중단",
      primaryTarget: "focus_execute",
      primaryLabel: "충돌 카드 보기",
    });
  }

  if (input.mergeChecks?.merge_disabled || oracleFailed) {
    const reason =
      input.mergeChecks?.merge_disabled_reason ??
      "Oracle FAIL — Work에서 재검증 또는 repair 흐름을 선택하세요.";
    return blockedWorkDecision({
      eyebrow: oracleFailed ? "Verify failed" : "Merge blocked",
      title: oracleFailed
        ? "검증 실패를 해결해야 합니다"
        : "merge check가 실패했습니다",
      detail: reason,
      approve: "실패 원인 수정 후 재검증",
      verified: oracleFailed ? "Oracle FAIL" : "merge check 실패",
      primaryTarget: oracleFailed ? "focus_execute" : "focus_checks",
      primaryLabel: oracleFailed ? "재검증 위치 보기" : "Checks 보기",
      secondaryTarget: "focus_evidence",
      secondaryLabel: "Evidence 보기",
    });
  }

  if (planApprovalPending(input)) {
    return workDecisionSummary({
      kind: "approval_required",
      eyebrow: "Approval required",
      title: "plan.md 승인이 필요합니다",
      detail: "Human 승인 후 dry-run과 execute를 진행할 수 있습니다.",
      whatToApprove: "현재 plan.md",
      whyBlocked: "Human plan approval 대기",
      verificationStatus: "execute 전",
      primaryTarget: "focus_plan_approval",
      primaryLabel: "Plan 승인 보기",
      approve: ["Plan approval", "목표와 완료 기준을 확인하세요.", "active"],
      blocked: [
        "승인 대기",
        "승인 전 execute 전송이 잠겨 있습니다.",
        "blocked",
      ],
      verified: ["검증 전", "승인 후 execute 결과를 검증합니다.", "idle"],
    });
  }

  if (active) {
    const label =
      active.status === "review_required"
        ? "산출물 확인 후 승인"
        : "Merge 승인";
    return workDecisionSummary({
      kind: "approval_required",
      eyebrow: "Approval required",
      title: "execute 결과 승인이 필요합니다",
      detail: active.action_what ?? "diff와 검증 산출물을 확인하세요.",
      whatToApprove: label,
      whyBlocked: "Human merge approval 대기",
      verificationStatus: oraclePassed ? "Oracle PASS" : "merge 전 검증 대기",
      primaryTarget: "focus_execute",
      primaryLabel: "승인 카드 보기",
      secondaryTarget: "focus_evidence",
      secondaryLabel: "Evidence 보기",
      approve: [label, active.action_what ?? "pending execution", "active"],
      blocked: ["승인 대기", "Human 결정이 필요합니다.", "idle"],
      verified: [
        oraclePassed ? "PASS" : "대기",
        oraclePassed ? "Oracle 검증 기록이 있습니다." : "merge 후 확인합니다.",
        oraclePassed ? "ok" : "idle",
      ],
    });
  }

  if (latest?.status === "merged" || latest?.status === "review_required") {
    return workDecisionSummary({
      kind: "verifying",
      eyebrow: "Verify",
      title: "merge 결과 검증을 확인하세요",
      detail: latest.action_what ?? "Oracle 또는 evidence 상태를 확인합니다.",
      whatToApprove: "추가 승인 없음",
      whyBlocked: "검증 완료 전 done 아님",
      verificationStatus: oraclePassed ? "Oracle PASS" : "Oracle 대기",
      primaryTarget: "focus_execute",
      primaryLabel: "검증 카드 보기",
      secondaryTarget: "focus_evidence",
      secondaryLabel: "Evidence 보기",
      approve: ["없음", "Human merge 결정은 끝났습니다.", "ok"],
      blocked: ["검증 대기", "Oracle 결과를 확인하세요.", "idle"],
      verified: [
        oraclePassed ? "PASS" : "대기",
        oraclePassed ? "완료 기준을 통과했습니다." : "검증 중입니다.",
        oraclePassed ? "ok" : "active",
      ],
    });
  }

  if (latest?.status === "completed" && oraclePassed) {
    return workDecisionSummary({
      kind: "verified",
      eyebrow: "Verified",
      title: "결과가 검증됐습니다",
      detail:
        latest.action_what ?? "최근 execute가 Oracle PASS로 완료됐습니다.",
      whatToApprove: "승인할 항목 없음",
      whyBlocked: "막힘 없음",
      verificationStatus: "Oracle PASS",
      primaryTarget: "focus_evidence",
      primaryLabel: "Evidence 보기",
      approve: ["없음", "Human 결정이 남아 있지 않습니다.", "ok"],
      blocked: ["없음", "현재 Work gate는 열려 있습니다.", "ok"],
      verified: ["PASS", "Oracle 검증을 통과했습니다.", "ok"],
    });
  }

  return workDecisionSummary({
    kind: "ready",
    eyebrow: "Work ready",
    title: "다음 execute를 선택할 수 있습니다",
    detail: "plan.md의 지금 실행 항목을 dry-run으로 검토하세요.",
    whatToApprove: "승인 대기 없음",
    whyBlocked: "막힘 없음",
    verificationStatus: "새 execute 전",
    primaryTarget: "focus_plan",
    primaryLabel: "실행 후보 보기",
    approve: ["대기 없음", "dry-run 후 승인 항목이 생깁니다.", "idle"],
    blocked: ["없음", "execute 후보를 선택할 수 있습니다.", "ok"],
    verified: ["대기", "실행 후 Oracle로 확인합니다.", "idle"],
  });
}
