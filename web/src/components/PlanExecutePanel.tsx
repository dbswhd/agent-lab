import type { EvidenceEntry, MergeChecksPayload } from "../api/client";
import type { RoomTask } from "../api/client";
import { PlanExecuteDryRunBody } from "./PlanExecuteDryRunBody";
import { PlanExecuteHistoryList } from "./PlanExecuteHistoryList";
import { PlanExecutePendingCard } from "./PlanExecutePendingCard";
import { PlanTodoList } from "./PlanTodoList";
import { EvidenceTimeline } from "./EvidenceTimeline";
import { WorkspaceCard } from "./WorkspaceCard";
import { useLocale } from "../i18n/useLocale";
import { usePlanExecutePanel } from "../hooks/usePlanExecutePanel";

type Props = {
  sessionId: string;
  planMd?: string;
  run?: Record<string, unknown>;
  linkedTasks?: RoomTask[];
  cursorReady: boolean;
  disabled?: boolean;
  onUpdated: () => void;
  onChatRefClick?: (lineNumber: number) => void;
  onFocusTask?: (taskId: string) => void;
  onFocusObjection?: (objectionId: string, actionIndex?: number) => void;
  mergeChecks?: MergeChecksPayload | null;
  evidenceEntries?: EvidenceEntry[];
  workHookAlert?: { event: string; body: string; blocked: boolean } | null;
  onDismissWorkHookAlert?: () => void;
  onOpenDiff?: () => void;
  onOpenFiles?: () => void;
  onOpenFile?: (path: string) => void;
  sessionIdForObjections?: string;
  onObjectionResolved?: () => void;
  variant?: "tool" | "composer";
  planFileLabel?: string;
};

export function PlanExecutePanel({
  sessionId,
  planMd: _planMd = "",
  run,
  linkedTasks,
  cursorReady,
  disabled,
  onUpdated,
  onChatRefClick,
  onFocusTask,
  onFocusObjection,
  mergeChecks = null,
  evidenceEntries = [],
  workHookAlert = null,
  onDismissWorkHookAlert,
  onOpenDiff,
  onOpenFiles,
  onOpenFile,
  sessionIdForObjections,
  onObjectionResolved,
  variant = "tool",
  planFileLabel = "plan.md",
}: Props) {
  const { locale } = useLocale();
  const panel = usePlanExecutePanel({
    sessionId,
    run,
    linkedTasks,
    disabled,
    mergeChecks,
    onUpdated,
  });

  if (!cursorReady) {
    return (
      <div className="work-surface" role="note">
        <div className="plan-card plan-card--muted">
          plan 실행은 Cursor 에이전트(CURSOR_API_KEY + cursor-sdk)가 필요합니다.
        </div>
      </div>
    );
  }

  return (
    <div
      className={[
        "work-surface",
        variant === "composer" ? "work-surface--composer" : "",
      ]
        .filter(Boolean)
        .join(" ")}
      aria-label="plan 실행"
    >
      {workHookAlert ? (
        <div
          className={`work-hook-alert${workHookAlert.blocked ? " work-hook-alert--blocked" : ""}`}
          role={workHookAlert.blocked ? "alert" : "status"}
        >
          <strong>{workHookAlert.event}</strong>
          <p>{workHookAlert.body}</p>
          {onDismissWorkHookAlert ? (
            <button
              type="button"
              className="btn btn--sm btn--ghost"
              onClick={onDismissWorkHookAlert}
            >
              닫기
            </button>
          ) : null}
        </div>
      ) : null}
      {panel.activePending || panel.historyRows[0] ? (
        <WorkspaceCard
          execution={panel.activePending ?? panel.historyRows[0]!}
          mergeChecks={mergeChecks}
          onOpenDiff={onOpenDiff}
          onOpenFiles={onOpenFiles}
          onOpenFile={onOpenFile}
        />
      ) : null}
      <PlanTodoList
        rows={panel.todoRows}
        progress={panel.todoProgress}
        diffRollup={panel.todoDiffRollup}
        locale={locale}
        variant={variant}
        loading={panel.loadingActions}
        busy={panel.busy}
        selectedKey={panel.selectedKey}
        disabled={panel.actionDisabled}
        planFileLabel={planFileLabel}
        onSelect={panel.setSelectedKey}
        onPlanFileClick={() => {
          if (onOpenFile) onOpenFile(planFileLabel);
          else onOpenFiles?.();
        }}
        defaultExpanded={!panel.activePending && !panel.busy}
      >
        <PlanExecuteDryRunBody
          sessionId={sessionId}
          loadingActions={panel.loadingActions}
          hasNowSection={panel.hasNowSection}
          hasDryRun={panel.hasDryRun}
          recommended={panel.recommended}
          nowHasOnlyGates={panel.nowHasOnlyGates}
          linkedForSelected={panel.linkedForSelected}
          selectedOpenBlocks={panel.selectedOpenBlocks}
          objectionBlock={panel.objectionBlock}
          planSnapshot={panel.planSnapshot}
          isolationBlock={panel.isolationBlock}
          activePending={panel.activePending}
          executeWorkspace={panel.executeWorkspace}
          disabled={disabled}
          busy={panel.busy}
          selectedKey={panel.selectedKey}
          sessionIdForObjections={sessionIdForObjections}
          onFocusTask={onFocusTask}
          onFocusObjection={onFocusObjection}
          onObjectionResolved={onObjectionResolved}
          onUpdated={onUpdated}
          onApprovePlanSnapshot={() => void panel.handleApprovePlanSnapshot()}
          onRejectPlanSnapshot={() => void panel.handleRejectPlanSnapshot()}
          onDryRun={() => void panel.handleDryRun()}
          onIsolationOverride={() => void panel.handleIsolationOverride()}
          onDismissIsolationBlock={() => panel.setIsolationBlock(null)}
        />
      </PlanTodoList>
      {panel.activePending ? (
        <PlanExecutePendingCard
          activePending={panel.activePending}
          pendingAction={panel.pendingAction}
          linkedForPending={panel.linkedForPending}
          sessionId={sessionId}
          mergeChecks={mergeChecks}
          approvalGate={panel.approvalGate}
          approveBlocked={panel.approveBlocked}
          mergeBlockTitle={panel.mergeBlockTitle}
          pendingDiffHunks={panel.pendingDiffHunks}
          artifactsReviewConfirmed={panel.artifactsReviewConfirmed}
          setArtifactsReviewConfirmed={panel.setArtifactsReviewConfirmed}
          reviseComment={panel.reviseComment}
          setReviseComment={panel.setReviseComment}
          reviseHunkId={panel.reviseHunkId}
          setReviseHunkId={panel.setReviseHunkId}
          reviseError={panel.reviseError}
          revising={panel.revising}
          busy={panel.busy}
          disabled={disabled}
          historyVisible={panel.historyVisible}
          storedActions={panel.storedActions}
          onUpdated={onUpdated}
          onChatRefClick={onChatRefClick}
          onFocusTask={onFocusTask}
          onOpenDiff={onOpenDiff}
          onOpenFiles={onOpenFiles}
          onResolve={(vote) => void panel.handleResolve(vote)}
          onRevisePending={() => void panel.handleRevisePending()}
          onMergeConfirm={() => void panel.handleMergeConfirm()}
          onMergeAbort={() => void panel.handleMergeAbort()}
          onReverify={(executionId) => void panel.handleReverify(executionId)}
          onIsolationOverride={(executionId) =>
            void panel.handleIsolationOverride(executionId)
          }
        />
      ) : null}

      {!panel.activePending && panel.historyRows.length ? (
        <PlanExecuteHistoryList
          historyRows={panel.historyRows}
          storedActions={panel.storedActions}
          busy={panel.busy}
          onChatRefClick={onChatRefClick}
          onReverify={(executionId) => void panel.handleReverify(executionId)}
        />
      ) : null}

      <EvidenceTimeline entries={evidenceEntries} compact />

      {panel.error ? <p className="plan-card__error">{panel.error}</p> : null}
    </div>
  );
}
