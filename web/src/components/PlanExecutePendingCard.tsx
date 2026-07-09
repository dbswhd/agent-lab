import type { Dispatch, SetStateAction } from "react";
import type {
  MergeChecksPayload,
  PlanExecutionRecord,
  RoomTask,
} from "../api/client";
import {
  AdversarialBadge,
  ApplyIsolationBanner,
  ExternalHandoffBadge,
  PlanLinkedTaskLine,
  WorktreePendingBanner,
  diffHunks,
  execStatusKey,
  formatPathList,
  oracleStatus,
  oracleStatusLabel,
  reviewRequiredLabel,
  statusLabel,
} from "./PlanExecutePanelSupport";
import { PlanAgentResponse } from "./PlanAgentResponse";
import { PlanDiffStat } from "./PlanDiffStat";
import { PlanActionContext } from "./PlanActionContext";
import {
  executionHistoryTitle,
  executionContextFields,
  formatExecutionTime,
  resolveExecutionAction,
  type StoredPlanAction,
} from "../utils/planExecuteHistory";
import type { ExecuteApprovalGate } from "../utils/executeApprovalGate";
import { WorkPlanIcon } from "./WorkPlanIcon";
import { UnifiedDiff } from "./UnifiedDiff";
import { MergeChecksPanel } from "./MergeChecksPanel";
import { TrustAutoMergeBar } from "./TrustAutoMergeBar";
import { EvidenceGatesPanel } from "./EvidenceGatesPanel";
import {
  executionApproveLabel,
  executionRejectLabel,
  isWorktreeExecution,
  mergeConflictFiles,
} from "../utils/planExecuteWorktree";

type DiffHunk = ReturnType<typeof diffHunks>[number];

type Props = {
  activePending: PlanExecutionRecord;
  pendingAction: StoredPlanAction | null;
  linkedForPending: RoomTask | undefined;
  sessionId: string;
  mergeChecks: MergeChecksPayload | null;
  approvalGate: ExecuteApprovalGate;
  approveBlocked: boolean;
  mergeBlockTitle?: string;
  pendingDiffHunks: DiffHunk[];
  artifactsReviewConfirmed: boolean;
  setArtifactsReviewConfirmed: Dispatch<SetStateAction<boolean>>;
  reviseComment: string;
  setReviseComment: Dispatch<SetStateAction<string>>;
  reviseHunkId: string;
  setReviseHunkId: Dispatch<SetStateAction<string>>;
  reviseError: string | null;
  revising: boolean;
  busy: boolean;
  disabled?: boolean;
  historyVisible: PlanExecutionRecord[];
  storedActions: StoredPlanAction[];
  onUpdated: () => void;
  onChatRefClick?: (lineNumber: number) => void;
  onFocusTask?: (taskId: string) => void;
  onOpenDiff?: () => void;
  onOpenFiles?: () => void;
  onResolve: (vote: "approve" | "reject") => void;
  onRevisePending: () => void;
  onMergeConfirm: () => void;
  onMergeAbort: () => void;
  onReverify: (executionId: string) => void;
  onIsolationOverride: (executionId: string) => void;
};

export function PlanExecutePendingCard({
  activePending,
  pendingAction,
  linkedForPending,
  sessionId,
  mergeChecks,
  approvalGate,
  approveBlocked,
  mergeBlockTitle,
  pendingDiffHunks,
  artifactsReviewConfirmed,
  setArtifactsReviewConfirmed,
  reviseComment,
  setReviseComment,
  reviseHunkId,
  setReviseHunkId,
  reviseError,
  revising,
  busy,
  disabled,
  historyVisible,
  storedActions,
  onUpdated,
  onChatRefClick,
  onFocusTask,
  onOpenDiff,
  onOpenFiles,
  onResolve,
  onRevisePending,
  onMergeConfirm,
  onMergeAbort,
  onReverify,
  onIsolationOverride,
}: Props) {
  return (
    <div
      className="exec-card"
      id="work-execute-queue"
      role="region"
      aria-label="승인 대기"
    >
      <div className="exec-card__head">
        <span className="exec-card__title">
          <WorkPlanIcon name="bolt" size={16} />
          {executionHistoryTitle(activePending, pendingAction)}
        </span>
        <span
          className={`exec-status exec-status--${execStatusKey(activePending.status)}`}
        >
          <span className="dot dot--warn" aria-hidden />
          {statusLabel(activePending.status, activePending)}
        </span>
      </div>
      <div className="exec-card__body">
        <ApplyIsolationBanner row={activePending} />
        <WorktreePendingBanner row={activePending} />
        <PlanLinkedTaskLine task={linkedForPending} onFocusTask={onFocusTask} />
        {activePending.pre_verify?.blocked ||
        (activePending.pre_verify?.feedback &&
          !activePending.pre_verify?.blocked) ? (
          <p
            className={
              activePending.pre_verify?.blocked
                ? "work-exec-pending__pre-verify work-exec-pending__pre-verify--blocked"
                : "work-exec-pending__pre-verify"
            }
            role={activePending.pre_verify?.blocked ? "alert" : "status"}
          >
            {activePending.pre_verify?.blocked
              ? `실행 전 검증 차단: ${activePending.pre_verify.feedback || "pre_execute hook"}`
              : `실행 전 검증: ${activePending.pre_verify?.feedback}`}
          </p>
        ) : null}
        <AdversarialBadge row={activePending} />
        <ExternalHandoffBadge row={activePending} />
        <MergeChecksPanel checks={mergeChecks} />
        <TrustAutoMergeBar
          sessionId={sessionId}
          executionId={activePending.id}
          onMerged={onUpdated}
        />
        <EvidenceGatesPanel gates={activePending.evidence_gates} />
        <PlanActionContext
          {...executionContextFields(activePending, pendingAction)}
          onRefClick={onChatRefClick}
        />
        {activePending.draft_summary ? (
          <PlanAgentResponse
            text={activePending.draft_summary}
            className="work-exec-pending__summary"
          />
        ) : null}
        {activePending.agent_log?.length ? (
          <details className="work-exec-pending__log" open>
            <summary>
              Cursor 로그 ({activePending.executor_label ?? "Cursor"} ·{" "}
              {activePending.agent_log.length})
            </summary>
            <ol className="work-exec-agent-log">
              {activePending.agent_log.map((line, i) => (
                <li key={`${activePending.id}-log-${i}`}>{line}</li>
              ))}
            </ol>
          </details>
        ) : null}
        {activePending.touched_paths?.length ? (
          <p className="work-exec-pending__paths">
            변경 파일: {formatPathList(activePending.touched_paths)}
          </p>
        ) : (
          <p className="work-exec-pending__paths work-exec-pending__paths--empty">
            소스 diff 없음 (스냅샷 diff 없음)
          </p>
        )}
        {activePending.artifact_touched_paths?.length ? (
          <p className="work-exec-pending__paths">
            검증 산출물: {formatPathList(activePending.artifact_touched_paths)}
          </p>
        ) : null}
        {activePending.needs_artifact_review ? (
          <p className="work-exec-pending__artifact-note" role="note">
            소스 파일 변경은 없지만 PDF/break-report 확인이 필요합니다. 승인 시
            &quot;{reviewRequiredLabel(activePending)}&quot;로 기록됩니다.
            {activePending.verification_paths?.length
              ? ` (모니터: ${formatPathList(activePending.verification_paths)})`
              : ""}
          </p>
        ) : null}
        {approvalGate.blocked && approvalGate.reason ? (
          <p className="exec-gate-hint" role="alert">
            <WorkPlanIcon name="alert" size={13} />
            {approvalGate.reason}
          </p>
        ) : null}
        {activePending.needs_artifact_review ? (
          <div
            className={`exec-verify${artifactsReviewConfirmed ? " is-confirmed" : ""}`}
          >
            <div className="exec-verify__line">
              <WorkPlanIcon name="doc" size={14} />
              <code className="exec-verify__path">
                {approvalGate.pdfPath ?? "—"}
              </code>
              {approvalGate.pageCount != null ? (
                <span className="badge">{approvalGate.pageCount}p</span>
              ) : null}
              {oracleStatus(activePending) ? (
                <span
                  className={`exec-verify__oracle exec-verify__oracle--${
                    oracleStatus(activePending) === "passed" ||
                    oracleStatus(activePending) === "pass"
                      ? "ok"
                      : "fail"
                  }`}
                >
                  <span className="dot dot--ok" aria-hidden />
                  {oracleStatusLabel(oracleStatus(activePending))}
                </span>
              ) : null}
            </div>
            <label className="exec-verify__confirm">
              <input
                type="checkbox"
                className="checkbox"
                checked={artifactsReviewConfirmed}
                onChange={(event) =>
                  setArtifactsReviewConfirmed(event.target.checked)
                }
              />
              PDF·페이지 수·산출물을 확인했습니다
            </label>
          </div>
        ) : null}
        {activePending.paths_outside_expected?.length ? (
          <p className="work-exec-pending__warn">
            예상 범위 밖: {formatPathList(activePending.paths_outside_expected)}
          </p>
        ) : null}
        {activePending.status === "merge_conflict" ? (
          <div
            className="work-exec-merge-conflict"
            role="alert"
            aria-label="merge 충돌"
          >
            <p className="work-exec-merge-conflict__lead">
              main 병합 중 충돌이 발생했습니다. 저장소에서 충돌을 해결한 뒤 다시
              시도하세요.
            </p>
            {mergeConflictFiles(activePending).length ? (
              <ul className="work-exec-merge-conflict__files">
                {mergeConflictFiles(activePending).map((path) => (
                  <li key={path}>
                    <code>{path}</code>
                  </li>
                ))}
              </ul>
            ) : null}
          </div>
        ) : null}
        {activePending.diff_stat ? (
          <PlanDiffStat text={activePending.diff_stat} />
        ) : null}
        {activePending.diff ? (
          <div className="exec-diff-wrap">
            <div className="exec-diff__head">
              <WorkPlanIcon name="gitMerge" size={14} />
              Diff preview
              {onOpenDiff ? (
                <button
                  type="button"
                  className="plan-btn plan-btn--ghost"
                  onClick={onOpenDiff}
                >
                  Diff 탭
                </button>
              ) : null}
              {onOpenFiles ? (
                <button
                  type="button"
                  className="plan-btn plan-btn--ghost"
                  onClick={onOpenFiles}
                >
                  Files
                </button>
              ) : null}
            </div>
            <UnifiedDiff
              diff={activePending.diff}
              activeHunkId={reviseHunkId || undefined}
            />
          </div>
        ) : null}
        {activePending.status === "pending_approval" &&
        isWorktreeExecution(activePending) &&
        activePending.diff ? (
          <div className="work-exec-revise">
            <div className="work-exec-revise__controls">
              <select
                aria-label="재작업할 diff hunk"
                value={reviseHunkId}
                disabled={busy}
                onChange={(event) => setReviseHunkId(event.target.value)}
              >
                <option value="">전체 diff</option>
                {pendingDiffHunks.map((hunk, index) => (
                  <option key={hunk.id} value={hunk.id}>
                    hunk {index + 1} · {hunk.ref}
                  </option>
                ))}
              </select>
              <textarea
                aria-label="diff 재작업 요청"
                value={reviseComment}
                disabled={busy}
                rows={2}
                maxLength={2000}
                placeholder="수정 요청"
                onChange={(event) => setReviseComment(event.target.value)}
              />
            </div>
            {reviseError ? (
              <p className="work-exec-revise__error" role="alert">
                {reviseError}
              </p>
            ) : null}
          </div>
        ) : null}
        <div className="exec-actions">
          {activePending.status === "merge_conflict" ? (
            <>
              <button
                type="button"
                className="plan-btn plan-btn--ok"
                disabled={disabled || busy}
                onClick={() => onMergeConfirm()}
              >
                Conflict 해결 완료
              </button>
              <button
                type="button"
                className="plan-btn plan-btn--danger"
                disabled={disabled || busy}
                onClick={() => onMergeAbort()}
              >
                Merge 취소
              </button>
            </>
          ) : (
            <>
              <button
                type="button"
                className="plan-btn plan-btn--danger"
                disabled={disabled || busy}
                onClick={() => onResolve("reject")}
              >
                <WorkPlanIcon name="x" size={14} />
                {executionRejectLabel(activePending)}
              </button>
              <button
                type="button"
                className="plan-btn"
                disabled={
                  disabled ||
                  busy ||
                  !reviseComment.trim() ||
                  !activePending.diff
                }
                onClick={() => onRevisePending()}
              >
                <WorkPlanIcon name="refresh" size={14} />
                {revising ? "재작업 중…" : "Revise"}
              </button>
              <button
                type="button"
                className="plan-btn plan-btn--ok"
                disabled={disabled || busy || approveBlocked}
                title={approvalGate.reason ?? mergeBlockTitle ?? undefined}
                onClick={() => onResolve("approve")}
              >
                <WorkPlanIcon name="gitMerge" size={14} />
                {executionApproveLabel(activePending)}
              </button>
            </>
          )}
        </div>
        {historyVisible.length ? (
          <details className="exec-history-details">
            <summary>실행 기록</summary>
            <div className="exec-history">
              {historyVisible.map((row) => {
                const action = resolveExecutionAction(row, storedActions);
                const completedAt = formatExecutionTime(
                  row.completed_at || row.started_at,
                );
                return (
                  <div key={row.id} className="exec-history__row">
                    <WorkPlanIcon name="activity" size={13} />
                    {executionHistoryTitle(row, action)}
                    {completedAt ? (
                      <span className="exec-history__time">{completedAt}</span>
                    ) : null}
                  </div>
                );
              })}
            </div>
          </details>
        ) : null}
        <div className="exec-extra-actions">
          {oracleStatus(activePending) === "failed" ||
          oracleStatus(activePending) === "fail" ? (
            <button
              type="button"
              className="plan-btn"
              disabled={busy}
              onClick={() => onReverify(activePending.id)}
            >
              <WorkPlanIcon name="eyeCheck" size={14} />
              Oracle 재검증
            </button>
          ) : null}
          {isWorktreeExecution(activePending) ? (
            <button
              type="button"
              className="plan-btn"
              disabled={disabled || busy || !activePending.id}
              onClick={() => onIsolationOverride(activePending.id)}
            >
              <WorkPlanIcon name="unlock" size={14} />
              격리 오버라이드
            </button>
          ) : null}
        </div>
      </div>
    </div>
  );
}
