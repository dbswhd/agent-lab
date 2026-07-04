import { useCallback, useEffect, useMemo, useState } from "react";
import {
  abortPlanExecutionMerge,
  approvePendingPlan,
  confirmPlanExecutionMerge,
  fetchPlanActions,
  PlanSnapshotRequiredError,
  PlanExecuteDryRunError,
  overridePlanExecutionIsolation,
  reverifyPlanExecution,
  rejectPendingPlan,
  revisePendingPlan,
  resolvePlanExecution,
  runPlanDryRun,
  type PendingPlanRecord,
  type PlanActionItem,
  type PlanExecutionRecord,
  type RoomTask,
} from "../api/client";
import {
  AdversarialBadge,
  ApplyIsolationBanner,
  EXECUTION_HISTORY_LIMIT,
  ExternalHandoffBadge,
  OracleBadge,
  PlanLinkedTaskLine,
  PlanObjectionAlert,
  WorktreePendingBanner,
  actionKey,
  diffHunks,
  execStatusKey,
  executePermissions,
  formatPathList,
  linkedTaskForAction,
  openBlockObjectionsForAction,
  oracleStatus,
  oracleStatusLabel,
  parseActionKey,
  reviewRequiredLabel,
  statusLabel,
} from "./PlanExecutePanelSupport";
import { PlanAgentResponse } from "./PlanAgentResponse";
import { PlanDiffStat } from "./PlanDiffStat";
import { PlanActionContext } from "./PlanActionContext";
import {
  executionHistoryBadge,
  executionHistoryTitle,
  executionContextFields,
  formatExecutionTime,
  resolveExecutionAction,
  type StoredPlanAction,
} from "../utils/planExecuteHistory";
import { executionApprovalGate } from "../utils/executeApprovalGate";
import { formatPlanExecuteError } from "../utils/planExecuteErrors";
import { WorkPlanIcon } from "./WorkPlanIcon";
import { SideBySideDiff } from "./SideBySideDiff";
import { PlanTodoList } from "./PlanTodoList";
import { useLocale } from "../i18n/useLocale";
import {
  buildPlanTodoRows,
  planTodoProgress,
  resolvePlanDiffRollup,
} from "../utils/planTodoView";
import { MergeChecksPanel } from "./MergeChecksPanel";
import { TrustAutoMergeBar } from "./TrustAutoMergeBar";
import { EvidenceGatesPanel } from "./EvidenceGatesPanel";
import { EvidenceTimeline } from "./EvidenceTimeline";
import type { EvidenceEntry, MergeChecksPayload } from "../api/client";
import {
  executionApproveLabel,
  executionRejectLabel,
  findActiveExecution,
  isWorktreeExecution,
  mergeConflictFiles,
  mergedCommitSha,
} from "../utils/planExecuteWorktree";

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
  const [recommended, setRecommended] = useState<PlanActionItem | null>(null);
  const [nowItems, setNowItems] = useState<PlanActionItem[]>([]);
  const [roadmap, setRoadmap] = useState<PlanActionItem[]>([]);
  const [loadingActions, setLoadingActions] = useState(false);
  const [planSnapshot, setPlanSnapshot] = useState<PendingPlanRecord | null>(
    null,
  );
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [pending, setPending] = useState<PlanExecutionRecord | null>(null);
  const [isolationBlock, setIsolationBlock] =
    useState<PlanExecuteDryRunError | null>(null);
  const [objectionBlock, setObjectionBlock] =
    useState<PlanExecuteDryRunError | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reviseComment, setReviseComment] = useState("");
  const [reviseHunkId, setReviseHunkId] = useState("");
  const [reviseError, setReviseError] = useState<string | null>(null);
  const [revising, setRevising] = useState(false);
  const [artifactsReviewConfirmed, setArtifactsReviewConfirmed] =
    useState(false);

  const executions = useMemo(
    () => (run?.executions as PlanExecutionRecord[] | undefined) ?? [],
    [run],
  );

  const storedActions = useMemo(
    () => (run?.actions as StoredPlanAction[] | undefined) ?? [],
    [run],
  );

  const historyRows = useMemo(
    () =>
      [...executions]
        .filter(
          (row) =>
            row.status !== "pending_approval" &&
            row.status !== "merge_conflict",
        )
        .reverse(),
    [executions],
  );

  const historyVisible = historyRows.slice(0, EXECUTION_HISTORY_LIMIT);
  const historyHiddenCount = Math.max(
    0,
    historyRows.length - historyVisible.length,
  );

  const pendingFromRun = useMemo(
    () => findActiveExecution(executions),
    [executions],
  );

  const activePending = pending ?? pendingFromRun;
  const pendingAction = activePending
    ? resolveExecutionAction(activePending, storedActions)
    : null;
  const approvalGate = executionApprovalGate(activePending);
  const mergeBlocked = Boolean(mergeChecks?.merge_disabled);
  const approveBlocked =
    approvalGate.blocked ||
    mergeBlocked ||
    Boolean(activePending?.needs_artifact_review && !artifactsReviewConfirmed);
  const mergeBlockTitle =
    mergeChecks?.merge_disabled_reason ??
    (mergeBlocked ? "Merge checks failed" : undefined);
  const pendingDiffHunks = useMemo(
    () => diffHunks(activePending?.diff),
    [activePending?.diff],
  );

  const refreshActions = useCallback(async () => {
    setLoadingActions(true);
    setError(null);
    try {
      const res = await fetchPlanActions(sessionId);
      setRecommended(res.recommended);
      setNowItems(res.now ?? []);
      setRoadmap(res.roadmap);
      const executableItems = [
        ...(res.recommended ? [res.recommended] : []),
        ...(res.now ?? []).filter((item) => item.executable !== false),
        ...res.roadmap.filter((item) => item.executable !== false),
        ...res.actions.filter((item) => item.executable !== false),
      ];
      const seen = new Set<string>();
      const uniqueExecutable = executableItems.filter((item) => {
        const key = actionKey(item);
        if (seen.has(key)) return false;
        seen.add(key);
        return true;
      });
      setSelectedKey((prev) => {
        if (prev && uniqueExecutable.some((item) => actionKey(item) === prev)) {
          return prev;
        }
        if (res.recommended) return actionKey(res.recommended);
        const first = uniqueExecutable[0];
        return first ? actionKey(first) : null;
      });
    } catch (e) {
      setError(String(e));
    } finally {
      setLoadingActions(false);
    }
  }, [sessionId]);

  const lastPlanUpdateTs = useMemo(() => {
    const lpu = run?.last_plan_update as
      | { completed_at?: string; ts?: string }
      | undefined;
    return lpu?.completed_at || lpu?.ts || null;
  }, [run?.last_plan_update]);

  useEffect(() => {
    void refreshActions();
  }, [refreshActions, lastPlanUpdateTs]);

  useEffect(() => {
    setPending(null);
    setPlanSnapshot(null);
    setIsolationBlock(null);
    setObjectionBlock(null);
  }, [sessionId]);

  useEffect(() => {
    setReviseComment("");
    setReviseHunkId("");
    setReviseError(null);
    setArtifactsReviewConfirmed(false);
  }, [activePending?.id]);

  async function handleDryRun() {
    if (selectedKey == null || activePending) return;
    const parsed = parseActionKey(selectedKey);
    if (!parsed) return;
    setBusy(true);
    setError(null);
    setIsolationBlock(null);
    setObjectionBlock(null);
    const permissions = executePermissions();
    try {
      const res = await runPlanDryRun(sessionId, {
        actionIndex: parsed.index,
        actionKind: parsed.kind,
        permissions,
      });
      setPlanSnapshot(null);
      setPending(res.execution);
      onUpdated();
    } catch (e) {
      if (e instanceof PlanSnapshotRequiredError) {
        setPlanSnapshot(e.pendingPlan);
        setError(null);
      } else if (
        e instanceof PlanExecuteDryRunError &&
        [
          "worktree_unavailable",
          "base_branch_dirty",
          "paths_span_repos",
        ].includes(e.code)
      ) {
        setIsolationBlock(e);
        setError(null);
      } else if (
        e instanceof PlanExecuteDryRunError &&
        e.code === "open_objection"
      ) {
        setObjectionBlock(e);
        setError(null);
      } else {
        setError(formatPlanExecuteError(e));
      }
    } finally {
      setBusy(false);
    }
  }

  async function handleApprovePlanSnapshot() {
    if (!planSnapshot?.id) return;
    setBusy(true);
    setError(null);
    try {
      await approvePendingPlan(sessionId, planSnapshot.id);
      setPlanSnapshot(null);
    } catch (e) {
      setError(String(e));
      return;
    } finally {
      setBusy(false);
    }
    await handleDryRun();
  }

  async function handleRejectPlanSnapshot() {
    if (!planSnapshot?.id) return;
    setBusy(true);
    try {
      await rejectPendingPlan(sessionId, planSnapshot.id);
      setPlanSnapshot(null);
    } catch (e) {
      setError(formatPlanExecuteError(e));
    } finally {
      setBusy(false);
    }
  }

  async function handleResolve(vote: "approve" | "reject") {
    if (!activePending?.id) return;
    setBusy(true);
    setError(null);
    const permissions = executePermissions();
    try {
      await resolvePlanExecution(sessionId, {
        executionId: activePending.id,
        vote,
        permissions,
      });
      setPending(null);
      setSelectedKey(null);
      onUpdated();
      await refreshActions();
    } catch (e) {
      setError(formatPlanExecuteError(e));
    } finally {
      setBusy(false);
    }
  }

  async function handleRevisePending() {
    if (!activePending?.id || !reviseComment.trim()) return;
    const selectedHunk = pendingDiffHunks.find(
      (hunk) => hunk.id === reviseHunkId,
    );
    setBusy(true);
    setRevising(true);
    setError(null);
    setReviseError(null);
    try {
      const result = await revisePendingPlan(sessionId, activePending.id, {
        comment: reviseComment.trim(),
        chunkRef: selectedHunk?.ref,
        lineStart: selectedHunk?.lineStart,
        lineEnd: selectedHunk?.lineEnd,
        permissions: executePermissions(),
      });
      setPending(result.execution);
      onUpdated();
      await refreshActions();
    } catch (e) {
      setReviseError(formatPlanExecuteError(e));
    } finally {
      setRevising(false);
      setBusy(false);
    }
  }

  async function handleMergeAbort() {
    if (!activePending?.id) return;
    setBusy(true);
    setError(null);
    try {
      await abortPlanExecutionMerge(sessionId, activePending.id);
      setPending(null);
      setSelectedKey(null);
      onUpdated();
      await refreshActions();
    } catch (e) {
      setError(formatPlanExecuteError(e));
    } finally {
      setBusy(false);
    }
  }

  async function handleMergeConfirm() {
    if (!activePending?.id) return;
    setBusy(true);
    setError(null);
    try {
      await confirmPlanExecutionMerge(sessionId, activePending.id);
      setPending(null);
      setSelectedKey(null);
      onUpdated();
      await refreshActions();
    } catch (e) {
      setError(formatPlanExecuteError(e));
    } finally {
      setBusy(false);
    }
  }

  async function handleReverify(executionId: string) {
    setBusy(true);
    setError(null);
    try {
      await reverifyPlanExecution(sessionId, executionId, executePermissions());
      onUpdated();
      await refreshActions();
    } catch (e) {
      setError(formatPlanExecuteError(e));
    } finally {
      setBusy(false);
    }
  }

  async function handleIsolationOverride(executionId?: string) {
    const targetId = executionId ?? isolationBlock?.executionId;
    if (!targetId) {
      setError("blocked execution id가 없어 override를 실행할 수 없습니다.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const res = await overridePlanExecutionIsolation(sessionId, {
        executionId: targetId,
        mode: "snapshot_override",
        confirmation: "snapshot_override 비격리 실행",
        permissions: executePermissions(),
      });
      setPending(res.execution);
      setIsolationBlock(null);
      onUpdated();
    } catch (e) {
      setError(formatPlanExecuteError(e));
    } finally {
      setBusy(false);
    }
  }

  const executableItems = useMemo(() => {
    const items = [
      ...(recommended ? [recommended] : []),
      ...nowItems.filter((item) => item.executable !== false),
      ...roadmap.filter((item) => item.executable !== false),
    ];
    const seen = new Set<string>();
    return items.filter((item) => {
      const key = actionKey(item);
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  }, [recommended, nowItems, roadmap]);

  const hasDryRun = executableItems.length > 0;
  const hasNowSection = nowItems.length > 0;
  const nowHasOnlyGates =
    hasNowSection && !nowItems.some((item) => item.executable !== false);

  const selectedAction = useMemo(() => {
    if (!selectedKey) return null;
    return (
      executableItems.find((item) => actionKey(item) === selectedKey) ?? null
    );
  }, [executableItems, selectedKey]);

  const selectedOpenBlocks = useMemo(
    () => openBlockObjectionsForAction(run, selectedAction?.index),
    [run, selectedAction?.index],
  );

  const linkedForSelected = linkedTaskForAction(
    linkedTasks,
    selectedAction?.index ?? recommended?.index,
  );
  const linkedForPending = linkedTaskForAction(
    linkedTasks,
    pendingAction?.index ?? activePending?.action_index,
  );

  const executeWorkspace =
    selectedAction?.execute_workspace ?? recommended?.execute_workspace;

  const todoRows = useMemo(
    () =>
      buildPlanTodoRows({
        recommended,
        nowItems,
        roadmap,
        selectedKey,
        executions,
        activePending,
      }),
    [recommended, nowItems, roadmap, selectedKey, executions, activePending],
  );

  const todoProgress = useMemo(
    () => planTodoProgress(todoRows, activePending),
    [todoRows, activePending],
  );

  const todoDiffRollup = useMemo(
    () => resolvePlanDiffRollup({ activePending, executions }),
    [activePending, executions],
  );

  const actionDisabled = Boolean(disabled || busy || activePending);

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
      <PlanTodoList
        rows={todoRows}
        progress={todoProgress}
        diffRollup={todoDiffRollup}
        locale={locale}
        variant={variant}
        loading={loadingActions}
        busy={busy}
        selectedKey={selectedKey}
        disabled={actionDisabled}
        planFileLabel={planFileLabel}
        onSelect={setSelectedKey}
        onRefClick={onChatRefClick}
        onPlanFileClick={() => {
          if (onOpenFile) onOpenFile(planFileLabel);
          else onOpenFiles?.();
        }}
        defaultExpanded={!activePending && !busy}
      >
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

        <PlanLinkedTaskLine
          task={linkedForSelected}
          onFocusTask={onFocusTask}
        />

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
                onClick={() => void handleApprovePlanSnapshot()}
              >
                {busy ? "처리 중…" : "스냅샷 승인 → dry-run"}
              </button>
              <button
                type="button"
                className="plan-btn"
                disabled={busy}
                onClick={() => void handleRejectPlanSnapshot()}
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
                  setIsolationBlock(null);
                  void handleDryRun();
                }}
              >
                修復 후 재시도
              </button>
              <button
                type="button"
                className="plan-btn"
                disabled={disabled || busy || !isolationBlock.executionId}
                onClick={() => void handleIsolationOverride()}
              >
                이번만 비격리 실행…
              </button>
              <button
                type="button"
                className="plan-btn"
                disabled={busy}
                onClick={() => setIsolationBlock(null)}
              >
                취소
              </button>
            </div>
          </div>
        ) : null}

        {!activePending && hasDryRun && !planSnapshot ? (
          <div className="plan-actions-bar">
            {executeWorkspace?.label ? (
              <span className="plan-card__workspace">
                {executeWorkspace.label}
              </span>
            ) : null}
            <button
              type="button"
              className="plan-btn plan-btn--primary plan-btn--execute"
              disabled={disabled || busy || selectedKey == null}
              onClick={() => void handleDryRun()}
            >
              <WorkPlanIcon name="play" size={14} />
              {busy ? "Cursor 실행 중…" : "Execute"}
            </button>
          </div>
        ) : null}
      </PlanTodoList>
      {activePending ? (
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
            <PlanLinkedTaskLine
              task={linkedForPending}
              onFocusTask={onFocusTask}
            />
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
                검증 산출물:{" "}
                {formatPathList(activePending.artifact_touched_paths)}
              </p>
            ) : null}
            {activePending.needs_artifact_review ? (
              <p className="work-exec-pending__artifact-note" role="note">
                소스 파일 변경은 없지만 PDF/break-report 확인이 필요합니다. 승인
                시 &quot;{reviewRequiredLabel(activePending)}&quot;로
                기록됩니다.
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
                예상 범위 밖:{" "}
                {formatPathList(activePending.paths_outside_expected)}
              </p>
            ) : null}
            {activePending.status === "merge_conflict" ? (
              <div
                className="work-exec-merge-conflict"
                role="alert"
                aria-label="merge 충돌"
              >
                <p className="work-exec-merge-conflict__lead">
                  main 병합 중 충돌이 발생했습니다. 저장소에서 충돌을 해결한 뒤
                  다시 시도하세요.
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
                <SideBySideDiff
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
                    onClick={() => void handleMergeConfirm()}
                  >
                    Conflict 해결 완료
                  </button>
                  <button
                    type="button"
                    className="plan-btn plan-btn--danger"
                    disabled={disabled || busy}
                    onClick={() => void handleMergeAbort()}
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
                    onClick={() => void handleResolve("reject")}
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
                    onClick={() => void handleRevisePending()}
                  >
                    <WorkPlanIcon name="refresh" size={14} />
                    {revising ? "재작업 중…" : "Revise"}
                  </button>
                  <button
                    type="button"
                    className="plan-btn plan-btn--ok"
                    disabled={disabled || busy || approveBlocked}
                    title={approvalGate.reason ?? mergeBlockTitle ?? undefined}
                    onClick={() => void handleResolve("approve")}
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
                          <span className="exec-history__time">
                            {completedAt}
                          </span>
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
                  onClick={() => void handleReverify(activePending.id)}
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
                  onClick={() => void handleIsolationOverride(activePending.id)}
                >
                  <WorkPlanIcon name="unlock" size={14} />
                  격리 오버라이드
                </button>
              ) : null}
            </div>
          </div>
        </div>
      ) : null}

      {!activePending && historyRows.length ? (
        <details className="work-exec-history">
          <summary>
            실행 기록
            {historyHiddenCount ? ` · 최근 ${EXECUTION_HISTORY_LIMIT}건` : null}
          </summary>
          <ul className="work-exec-history__list">
            {historyVisible.map((row) => {
              const action = resolveExecutionAction(row, storedActions);
              const context = executionContextFields(row, action);
              const completedAt = formatExecutionTime(
                row.completed_at || row.started_at,
              );
              return (
                <li key={row.id} className="work-exec-history__item">
                  <div className="work-exec-history__title-row">
                    <span className="work-exec-history__badge">
                      {executionHistoryBadge(row)}
                    </span>
                    <strong className="work-exec-history__title">
                      {executionHistoryTitle(row, action)}
                    </strong>
                  </div>
                  <div className="work-exec-history__meta">
                    <span className="work-exec-history__status">
                      {statusLabel(row.status, row)}
                    </span>
                    {row.executor_label ? (
                      <span className="work-exec-history__executor">
                        {row.executor_label}
                      </span>
                    ) : null}
                    {completedAt ? (
                      <span className="work-exec-history__time">
                        {completedAt}
                      </span>
                    ) : null}
                    {mergedCommitSha(row) ? (
                      <span
                        className="work-exec-history__merge-sha"
                        title={mergedCommitSha(row) ?? undefined}
                      >
                        merge {(mergedCommitSha(row) ?? "").slice(0, 7)}
                      </span>
                    ) : null}
                  </div>
                  <PlanActionContext
                    {...context}
                    onRefClick={onChatRefClick}
                    compact
                  />
                  <AdversarialBadge row={row} />
                  <OracleBadge
                    row={row}
                    busy={busy}
                    onReverify={(executionId) =>
                      void handleReverify(executionId)
                    }
                  />
                  {row.touched_paths?.length ? (
                    <p className="work-exec-history__paths">
                      변경: {formatPathList(row.touched_paths)}
                    </p>
                  ) : null}
                  {row.agent_log?.length ? (
                    <details className="work-exec-history__log">
                      <summary>에이전트 로그 ({row.agent_log.length})</summary>
                      <ol className="work-exec-agent-log">
                        {row.agent_log.map((line, i) => (
                          <li key={`${row.id}-log-${i}`}>{line}</li>
                        ))}
                      </ol>
                    </details>
                  ) : null}
                  {row.agent_response || row.draft_summary ? (
                    <details className="work-exec-history__response">
                      <summary>에이전트 응답</summary>
                      <PlanAgentResponse
                        text={row.agent_response || row.draft_summary || ""}
                      />
                    </details>
                  ) : null}
                </li>
              );
            })}
          </ul>
        </details>
      ) : null}

      <EvidenceTimeline entries={evidenceEntries} compact />

      {error ? <p className="plan-card__error">{error}</p> : null}
    </div>
  );
}
