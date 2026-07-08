import type {
  PendingPlanRecord,
  PlanActionItem,
  RoomObjection,
  RoomTask,
} from "../api/client";
import {
  PlanLinkedTaskLine,
  PlanObjectionAlert,
} from "./PlanExecutePanelSupport";
import type { PlanExecuteDryRunError } from "../api/client";
import { WorkPlanIcon } from "./WorkPlanIcon";

type ExecuteWorkspace = PlanActionItem["execute_workspace"];

type Props = {
  sessionId: string;
  loadingActions: boolean;
  hasNowSection: boolean;
  hasDryRun: boolean;
  recommended: PlanActionItem | null;
  nowHasOnlyGates: boolean;
  linkedForSelected: RoomTask | undefined;
  selectedOpenBlocks: RoomObjection[];
  objectionBlock: PlanExecuteDryRunError | null;
  planSnapshot: PendingPlanRecord | null;
  isolationBlock: PlanExecuteDryRunError | null;
  activePending: unknown;
  executeWorkspace: ExecuteWorkspace | undefined;
  disabled?: boolean;
  busy: boolean;
  selectedKey: string | null;
  sessionIdForObjections?: string;
  onFocusTask?: (taskId: string) => void;
  onFocusObjection?: (objectionId: string, actionIndex?: number) => void;
  onObjectionResolved?: () => void;
  onUpdated: () => void;
  onApprovePlanSnapshot: () => void;
  onRejectPlanSnapshot: () => void;
  onDryRun: () => void;
  onIsolationOverride: () => void;
  onDismissIsolationBlock: () => void;
};

export function PlanExecuteDryRunBody({
  sessionId,
  loadingActions,
  hasNowSection,
  hasDryRun,
  recommended,
  nowHasOnlyGates,
  linkedForSelected,
  selectedOpenBlocks,
  objectionBlock,
  planSnapshot,
  isolationBlock,
  activePending,
  executeWorkspace,
  disabled,
  busy,
  selectedKey,
  sessionIdForObjections,
  onFocusTask,
  onFocusObjection,
  onObjectionResolved,
  onUpdated,
  onApprovePlanSnapshot,
  onRejectPlanSnapshot,
  onDryRun,
  onIsolationOverride,
  onDismissIsolationBlock,
}: Props) {
  return (
    <>
      {!loadingActions && !hasNowSection && !hasDryRun && !recommended ? (
        <p className="plan-card__muted">
          plan.md에 실행 액션이 없습니다. 토론·분석만 있으면{" "}
          <code>## 지금 실행</code> 섹션이 비어 있을 수 있습니다.
          Transcript에서 구현 항목을 합의한 뒤 다음 턴 plan 갱신을 확인하세요.
        </p>
      ) : null}

      {nowHasOnlyGates ? (
        <p className="plan-card__muted plan-card__gate-note">
          Human 확인 항목만 있습니다. Cursor dry-run은{" "}
          <strong>무엇을 / 어디서 / 검증</strong> 3필드 액션 필요.
        </p>
      ) : null}

      <PlanLinkedTaskLine task={linkedForSelected} onFocusTask={onFocusTask} />

      {selectedOpenBlocks.length ? (
        <PlanObjectionAlert
          title="이 action은 미해결 BLOCK으로 execute가 차단됩니다"
          message="이의를 수용하거나 기각한 뒤 dry-run 하세요."
          objections={selectedOpenBlocks}
          onFocusObjection={onFocusObjection}
          sessionIdForObjections={sessionIdForObjections ?? sessionId}
          onObjectionResolved={onObjectionResolved ?? onUpdated}
        />
      ) : null}

      {objectionBlock?.objections?.length ? (
        <PlanObjectionAlert
          title="dry-run이 미해결 이의로 차단됐습니다"
          message={objectionBlock.message}
          objections={objectionBlock.objections}
          onFocusObjection={onFocusObjection}
          sessionIdForObjections={sessionIdForObjections ?? sessionId}
          onObjectionResolved={onObjectionResolved ?? onUpdated}
        />
      ) : null}

      {planSnapshot ? (
        <div
          className="work-exec-plan-snapshot"
          role="region"
          aria-label="plan 스냅샷 승인"
        >
          <p className="work-exec-plan-snapshot__lead">
            dry-run 전에 아래 plan 실행 항목을 확인·승인하세요 (스냅샷).
          </p>
          <pre className="work-exec-plan-snapshot__body">
            {planSnapshot.snapshot_text ||
              `${planSnapshot.action_what}\n${planSnapshot.action_where}\n${planSnapshot.action_verify}`}
          </pre>
          <div className="work-exec-plan-snapshot__actions">
            <button
              type="button"
              className="plan-btn plan-btn--primary"
              disabled={disabled || busy}
              onClick={onApprovePlanSnapshot}
            >
              {busy ? "처리 중…" : "스냅샷 승인 → dry-run"}
            </button>
            <button
              type="button"
              className="plan-btn"
              disabled={busy}
              onClick={onRejectPlanSnapshot}
            >
              거부
            </button>
          </div>
        </div>
      ) : null}

      {isolationBlock ? (
        <div className="work-exec-isolation-modal" role="alertdialog">
          <p className="work-exec-isolation-modal__title">
            격리 worktree를 만들 수 없습니다
          </p>
          <p className="work-exec-isolation-modal__reason">
            {isolationBlock.code}: {isolationBlock.message}
          </p>
          {isolationBlock.remediation?.length ? (
            <p className="work-exec-isolation-modal__hint">
              {isolationBlock.remediation.join(" · ")}
            </p>
          ) : null}
          <div className="work-exec-isolation-modal__actions">
            <button
              type="button"
              className="plan-btn plan-btn--primary"
              disabled={disabled || busy}
              onClick={() => {
                onDismissIsolationBlock();
                onDryRun();
              }}
            >
              복구 후 재시도
            </button>
            <button
              type="button"
              className="plan-btn"
              disabled={disabled || busy || !isolationBlock.executionId}
              onClick={onIsolationOverride}
            >
              이번만 비격리 실행…
            </button>
            <button
              type="button"
              className="plan-btn"
              disabled={busy}
              onClick={onDismissIsolationBlock}
            >
              취소
            </button>
          </div>
        </div>
      ) : null}

      {!activePending && hasDryRun && !planSnapshot ? (
        <div className="plan-actions-bar">
          {executeWorkspace?.label ? (
            <span className="plan-card__workspace">{executeWorkspace.label}</span>
          ) : null}
          <button
            type="button"
            className="plan-btn plan-btn--primary plan-btn--execute"
            disabled={disabled || busy || selectedKey == null}
            onClick={onDryRun}
          >
            <WorkPlanIcon name="play" size={14} />
            {busy ? "Cursor 실행 중…" : "Execute"}
          </button>
        </div>
      ) : null}
    </>
  );
}
