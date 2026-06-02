import { useCallback, useEffect, useMemo, useState } from "react";
import {
  approvePendingPlan,
  fetchPlanActions,
  PlanSnapshotRequiredError,
  rejectPendingPlan,
  resolvePlanExecution,
  runPlanDryRun,
  type PendingPlanRecord,
  type PlanActionItem,
  type PlanExecutionRecord,
  type RoomTask,
} from "../api/client";
import type { AgentPermissions } from "../utils/agentPermissions";
import { fullAgentPermissions } from "../utils/agentPermissions";
import { PlanActionCard, PlanGateLine } from "./PlanActionCard";
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

type Props = {
  sessionId: string;
  run?: Record<string, unknown>;
  linkedTasks?: RoomTask[];
  cursorReady: boolean;
  disabled?: boolean;
  onUpdated: () => void;
  onChatRefClick?: (lineNumber: number) => void;
  onFocusTask?: (taskId: string) => void;
};

function linkedTaskForAction(
  tasks: RoomTask[] | undefined,
  actionIndex: number | undefined,
): RoomTask | undefined {
  if (actionIndex == null || !tasks?.length) return undefined;
  return (
    tasks.find(
      (t) =>
        t.plan_action_index === actionIndex &&
        t.status !== "completed" &&
        t.status !== "cancelled",
    ) ??
    tasks.find((t) => t.plan_action_index === actionIndex)
  );
}

function PlanLinkedTaskLine({
  task,
  onFocusTask,
}: {
  task: RoomTask | undefined;
  onFocusTask?: (taskId: string) => void;
}) {
  if (!task || !onFocusTask) return null;
  return (
    <p className="plan-execute-panel__linked-task">
      연결 작업:{" "}
      <button
        type="button"
        className="plan-execute-panel__linked-task-btn"
        onClick={() => onFocusTask(task.id)}
        title="작업 바로 이동"
      >
        {task.title}
      </button>
    </p>
  );
}

function formatPathList(paths: string[] | undefined, max = 3): string {
  if (!paths?.length) return "";
  if (paths.length <= max) return paths.join(", ");
  const head = paths.slice(0, max).join(", ");
  return `${head} +${paths.length - max} more`;
}

function roadmapLabel(item: PlanActionItem): string {
  if (item.executable === false) {
    return item.summary || item.what;
  }
  return item.what;
}

function executePermissions(): AgentPermissions {
  return fullAgentPermissions();
}

function reviewRequiredLabel(row: PlanExecutionRecord | null | undefined): string {
  if (!row) return "PDF 확인 후 승인";
  const artifacts = row.verification_artifacts;
  const pages =
    artifacts?.pdf_page_count ??
    (artifacts?.break_report as { baselinePdfPageCount?: number } | undefined)
      ?.baselinePdfPageCount;
  const pdfPath =
    artifacts?.pdf_path ??
    row.artifact_touched_paths?.find((p) => p.toLowerCase().endsWith(".pdf")) ??
    row.verification_paths?.find((p) => p.toLowerCase().endsWith(".pdf"));
  const pageBit = pages != null ? `${pages}p` : null;
  if (pdfPath && pageBit) {
    return `PDF 확인 후 승인 · ${pdfPath} (${pageBit})`;
  }
  if (pdfPath) {
    return `PDF 확인 후 승인 · ${pdfPath}`;
  }
  if (pageBit) {
    return `PDF 확인 후 승인 (${pageBit})`;
  }
  return "PDF 확인 후 승인";
}

function statusLabel(
  status: string | undefined,
  row?: PlanExecutionRecord | null,
): string {
  switch (status) {
    case "pending_approval":
      return "승인 대기";
    case "completed":
      return "완료";
    case "review_required":
      return reviewRequiredLabel(row);
    case "rejected":
      return "거부됨";
    case "failed":
      return "실패";
    default:
      return status || "—";
  }
}

function actionKey(item: Pick<PlanActionItem, "kind" | "index" | "recommended">): string {
  const kind = item.kind ?? (item.recommended ? "now" : "roadmap");
  return `${kind}:${item.index}`;
}

function parseActionKey(key: string): { kind: string; index: number } | null {
  const sep = key.indexOf(":");
  if (sep <= 0) return null;
  const kind = key.slice(0, sep);
  const index = Number(key.slice(sep + 1));
  if (!Number.isFinite(index) || index < 1) return null;
  return { kind, index };
}

const EXECUTION_HISTORY_LIMIT = 5;

export function PlanExecutePanel({
  sessionId,
  run,
  linkedTasks,
  cursorReady,
  disabled,
  onUpdated,
  onChatRefClick,
  onFocusTask,
}: Props) {
  const [recommended, setRecommended] = useState<PlanActionItem | null>(null);
  const [nowItems, setNowItems] = useState<PlanActionItem[]>([]);
  const [roadmap, setRoadmap] = useState<PlanActionItem[]>([]);
  const [loadingActions, setLoadingActions] = useState(false);
  const [planSnapshot, setPlanSnapshot] = useState<PendingPlanRecord | null>(
    null,
  );
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [pending, setPending] = useState<PlanExecutionRecord | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
        .filter((row) => row.status !== "pending_approval")
        .reverse(),
    [executions],
  );

  const historyVisible = historyRows.slice(0, EXECUTION_HISTORY_LIMIT);
  const historyHiddenCount = Math.max(0, historyRows.length - historyVisible.length);

  const pendingFromRun = useMemo(
    () =>
      [...executions]
        .reverse()
        .find((row) => row.status === "pending_approval") ?? null,
    [executions],
  );

  const activePending = pending ?? pendingFromRun;
  const pendingAction = activePending
    ? resolveExecutionAction(activePending, storedActions)
    : null;
  const approvalGate = executionApprovalGate(activePending);

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
    const lpu = run?.last_plan_update as { completed_at?: string; ts?: string } | undefined;
    return lpu?.completed_at || lpu?.ts || null;
  }, [run?.last_plan_update]);

  useEffect(() => {
    void refreshActions();
  }, [refreshActions, lastPlanUpdateTs]);

  useEffect(() => {
    setPending(null);
    setPlanSnapshot(null);
  }, [sessionId]);

  async function handleDryRun() {
    if (selectedKey == null || activePending) return;
    const parsed = parseActionKey(selectedKey);
    if (!parsed) return;
    setBusy(true);
    setError(null);
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
      } else {
        const err = e as Error & { preVerify?: { feedback?: string } };
        const fb = err.preVerify?.feedback;
        setError(fb ? `pre_execute: ${fb}` : String(e));
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
      setError(String(e));
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
      setError(String(e));
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
      executableItems.find((item) => actionKey(item) === selectedKey) ??
      null
    );
  }, [executableItems, selectedKey]);

  const linkedForSelected = linkedTaskForAction(
    linkedTasks,
    selectedAction?.index ?? recommended?.index,
  );
  const linkedForPending = linkedTaskForAction(
    linkedTasks,
    pendingAction?.index ?? activePending?.action_index,
  );

  const executeWorkspace = selectedAction?.execute_workspace ?? recommended?.execute_workspace;

  if (!cursorReady) {
    return (
      <div className="plan-execute-panel plan-execute-panel--muted" role="note">
        plan 실행은 Cursor 에이전트(CURSOR_API_KEY + cursor-sdk)가 필요합니다.
      </div>
    );
  }

  return (
    <div className="plan-execute-panel plan-doc" aria-label="plan 실행">
      {(hasDryRun || hasNowSection) && !loadingActions ? (
        <p className="plan-execute-panel__lead">
          <span>
            {hasDryRun
              ? `Cursor dry-run ${executableItems.length}건`
              : "Human 확인 항목"}
            {roadmap.length > 0 ? ` · 이후 ${roadmap.length}건` : ""}
          </span>
          {hasDryRun ? (
            <span className="plan-execute-panel__lead-hint">선택 → dry-run → 승인</span>
          ) : null}
        </p>
      ) : null}

      {loadingActions ? (
        <p className="plan-execute-panel__muted">액션 불러오는 중…</p>
      ) : !hasNowSection && !hasDryRun ? (
        <p className="plan-execute-panel__muted">
          `## 지금 실행` 또는 `## 다음에 할 일` 섹션이 없습니다.
        </p>
      ) : (
        <>
          {hasNowSection ? (
            <>
              <h2 className="plan-doc__h2 plan-execute-panel__section">지금 실행</h2>
              {nowHasOnlyGates ? (
                <p className="plan-execute-panel__muted plan-execute-panel__gate-note">
                  Human 확인 항목만 있습니다. Cursor dry-run은{" "}
                  <strong>무엇을 / 어디서 / 검증</strong> 3필드 액션 필요.
                </p>
              ) : null}
              {nowItems.map((item) =>
                item.executable !== false ? (
                  <PlanActionCard
                    key={actionKey(item)}
                    n={item.index}
                    what={item.what}
                    where={item.where}
                    verify={item.verify}
                    onRefClick={onChatRefClick}
                    variant="now"
                    selectable
                    radioName="plan-action"
                    checked={selectedKey === actionKey(item)}
                    selected={selectedKey === actionKey(item)}
                    disabled={Boolean(disabled || busy || activePending)}
                    onSelect={() => setSelectedKey(actionKey(item))}
                  />
                ) : (
                  <PlanGateLine
                    key={actionKey(item)}
                    n={item.index}
                    text={item.summary || item.what}
                    onRefClick={onChatRefClick}
                    variant="now"
                  />
                ),
              )}
            </>
          ) : recommended ? (
            <>
              <h2 className="plan-doc__h2 plan-execute-panel__section">지금 실행</h2>
              <PlanActionCard
                n={recommended.index}
                what={recommended.what}
                where={recommended.where}
                verify={recommended.verify}
                onRefClick={onChatRefClick}
                variant="now"
                selectable
                radioName="plan-action"
                checked={selectedKey === actionKey(recommended)}
                selected={selectedKey === actionKey(recommended)}
                disabled={Boolean(disabled || busy || activePending)}
                onSelect={() => setSelectedKey(actionKey(recommended))}
              />
            </>
          ) : null}

          {roadmap.length > 0 ? (
            <>
              <h2 className="plan-doc__h2 plan-execute-panel__section">실행 순서 (이후)</h2>
              <div className="plan-execute-roadmap">
                {roadmap.map((item) =>
                  item.executable !== false ? (
                    <PlanActionCard
                      key={actionKey(item)}
                      n={item.index}
                      what={item.what}
                      where={item.where}
                      verify={item.verify}
                      onRefClick={onChatRefClick}
                      selectable
                      radioName="plan-action"
                      checked={selectedKey === actionKey(item)}
                      selected={selectedKey === actionKey(item)}
                      disabled={Boolean(disabled || busy || activePending)}
                      onSelect={() => setSelectedKey(actionKey(item))}
                    />
                  ) : (
                    <PlanGateLine
                      key={actionKey(item)}
                      n={item.index}
                      text={roadmapLabel(item)}
                      onRefClick={onChatRefClick}
                    />
                  ),
                )}
              </div>
            </>
          ) : null}
        </>
      )}

      <PlanLinkedTaskLine task={linkedForSelected} onFocusTask={onFocusTask} />

      {planSnapshot ? (
        <div
          className="plan-execute-plan-snapshot"
          role="region"
          aria-label="plan 스냅샷 승인"
        >
          <p className="plan-execute-plan-snapshot__lead">
            dry-run 전에 아래 plan 실행 항목을 확인·승인하세요 (스냅샷).
          </p>
          <pre className="plan-execute-plan-snapshot__body">
            {planSnapshot.snapshot_text ||
              `${planSnapshot.action_what}\n${planSnapshot.action_where}\n${planSnapshot.action_verify}`}
          </pre>
          <div className="plan-execute-plan-snapshot__actions">
            <button
              type="button"
              className="room-plan-btn room-plan-btn--accent"
              disabled={disabled || busy}
              onClick={() => void handleApprovePlanSnapshot()}
            >
              {busy ? "처리 중…" : "스냅샷 승인 → dry-run"}
            </button>
            <button
              type="button"
              className="room-plan-btn"
              disabled={busy}
              onClick={() => void handleRejectPlanSnapshot()}
            >
              거부
            </button>
          </div>
        </div>
      ) : null}

      {!activePending && hasDryRun && !planSnapshot ? (
        <div className="plan-execute-panel__run-row">
          {executeWorkspace?.label ? (
            <span className="plan-execute-panel__workspace">
              {executeWorkspace.label}
            </span>
          ) : null}
          <button
            type="button"
            className="room-plan-btn room-plan-btn--accent plan-execute-panel__run"
            disabled={disabled || busy || selectedKey == null}
            onClick={() => void handleDryRun()}
          >
            {busy ? "Cursor 실행 중…" : "dry-run"}
          </button>
        </div>
      ) : null}

      {activePending ? (
        <div className="plan-execute-pending" role="region" aria-label="승인 대기">
          <PlanLinkedTaskLine task={linkedForPending} onFocusTask={onFocusTask} />
          {activePending.pre_verify?.blocked ||
          (activePending.pre_verify?.feedback &&
            !activePending.pre_verify?.blocked) ? (
            <p
              className={
                activePending.pre_verify?.blocked
                  ? "plan-execute-pending__pre-verify plan-execute-pending__pre-verify--blocked"
                  : "plan-execute-pending__pre-verify"
              }
              role={activePending.pre_verify?.blocked ? "alert" : "status"}
            >
              {activePending.pre_verify?.blocked
                ? `실행 전 검증 차단: ${activePending.pre_verify.feedback || "pre_execute hook"}`
                : `실행 전 검증: ${activePending.pre_verify?.feedback}`}
            </p>
          ) : null}
          <div className="plan-execute-pending__head">
            <div className="plan-execute-history__title-row">
              <span className="plan-execute-history__badge">
                {executionHistoryBadge(activePending)}
              </span>
              <strong className="plan-execute-history__title">
                {executionHistoryTitle(activePending, pendingAction)}
              </strong>
            </div>
            <span className="plan-execute-pending__status">
              {statusLabel(activePending.status, activePending)}
            </span>
          </div>
          <PlanActionContext
            {...executionContextFields(activePending, pendingAction)}
            onRefClick={onChatRefClick}
          />
          {activePending.draft_summary ? (
            <PlanAgentResponse
              text={activePending.draft_summary}
              className="plan-execute-pending__summary"
            />
          ) : null}
          {activePending.agent_log?.length ? (
            <details className="plan-execute-pending__log" open>
              <summary>
                Cursor 로그 ({activePending.executor_label ?? "Cursor"} ·{" "}
                {activePending.agent_log.length})
              </summary>
              <ol className="plan-execute-agent-log">
                {activePending.agent_log.map((line, i) => (
                  <li key={`${activePending.id}-log-${i}`}>{line}</li>
                ))}
              </ol>
            </details>
          ) : null}
          {activePending.touched_paths?.length ? (
            <p className="plan-execute-pending__paths">
              변경 파일: {formatPathList(activePending.touched_paths)}
            </p>
          ) : (
            <p className="plan-execute-pending__paths plan-execute-pending__paths--empty">
              소스 diff 없음 (스냅샷 diff 없음)
            </p>
          )}
          {activePending.artifact_touched_paths?.length ? (
            <p className="plan-execute-pending__paths">
              검증 산출물: {formatPathList(activePending.artifact_touched_paths)}
            </p>
          ) : null}
          {activePending.needs_artifact_review ? (
            <p className="plan-execute-pending__artifact-note" role="note">
              소스 파일 변경은 없지만 PDF/break-report 확인이 필요합니다. 승인 시
              &quot;{reviewRequiredLabel(activePending)}&quot;로 기록됩니다.
              {activePending.verification_paths?.length
                ? ` (모니터: ${formatPathList(activePending.verification_paths)})`
                : ""}
            </p>
          ) : null}
          {approvalGate.blocked && approvalGate.reason ? (
            <p className="plan-execute-pending__gate" role="alert">
              {approvalGate.reason}
            </p>
          ) : null}
          {activePending.needs_artifact_review ? (
            <div className="plan-execute-pending__verify" role="status">
              <span>
                PDF: {approvalGate.pdfPath ?? "—"}
                {approvalGate.pageCount != null
                  ? ` · ${approvalGate.pageCount}p`
                  : " · 페이지 수 —"}
              </span>
              <span>
                {approvalGate.artifactsOk ? "검증 OK" : "검증 대기"}
              </span>
            </div>
          ) : null}
          {activePending.paths_outside_expected?.length ? (
            <p className="plan-execute-pending__warn">
              예상 범위 밖: {formatPathList(activePending.paths_outside_expected)}
            </p>
          ) : null}
          {activePending.diff_stat ? (
            <PlanDiffStat text={activePending.diff_stat} />
          ) : null}
          {activePending.diff ? (
            <details className="plan-execute-pending__diff">
              <summary>로컬 diff</summary>
              <pre>{activePending.diff}</pre>
            </details>
          ) : null}
          <div className="plan-execute-pending__actions">
            <button
              type="button"
              className="room-plan-btn room-plan-btn--accent"
              disabled={disabled || busy || approvalGate.blocked}
              title={approvalGate.reason ?? undefined}
              onClick={() => void handleResolve("approve")}
            >
              승인 (변경 유지)
            </button>
            <button
              type="button"
              className="room-plan-btn"
              disabled={disabled || busy}
              onClick={() => void handleResolve("reject")}
            >
              거부 (되돌리기)
            </button>
          </div>
        </div>
      ) : null}

      {historyRows.length ? (
        <details className="plan-execute-history">
          <summary>
            실행 기록
            {historyHiddenCount ? ` · 최근 ${EXECUTION_HISTORY_LIMIT}건` : null}
          </summary>
          <ul className="plan-execute-history__list">
            {historyVisible.map((row) => {
                const action = resolveExecutionAction(row, storedActions);
                const context = executionContextFields(row, action);
                const completedAt = formatExecutionTime(
                  row.completed_at || row.started_at,
                );
                return (
                <li key={row.id} className="plan-execute-history__item">
                  <div className="plan-execute-history__title-row">
                    <span className="plan-execute-history__badge">
                      {executionHistoryBadge(row)}
                    </span>
                    <strong className="plan-execute-history__title">
                      {executionHistoryTitle(row, action)}
                    </strong>
                  </div>
                  <div className="plan-execute-history__meta">
                    <span className="plan-execute-history__status">
                      {statusLabel(row.status, row)}
                    </span>
                    {row.executor_label ? (
                      <span className="plan-execute-history__executor">
                        {row.executor_label}
                      </span>
                    ) : null}
                    {completedAt ? (
                      <span className="plan-execute-history__time">{completedAt}</span>
                    ) : null}
                  </div>
                  <PlanActionContext
                    {...context}
                    onRefClick={onChatRefClick}
                    compact
                  />
                  {row.touched_paths?.length ? (
                    <p className="plan-execute-history__paths">
                      변경: {formatPathList(row.touched_paths)}
                    </p>
                  ) : null}
                  {row.agent_log?.length ? (
                    <details className="plan-execute-history__log">
                      <summary>에이전트 로그 ({row.agent_log.length})</summary>
                      <ol className="plan-execute-agent-log">
                        {row.agent_log.map((line, i) => (
                          <li key={`${row.id}-log-${i}`}>{line}</li>
                        ))}
                      </ol>
                    </details>
                  ) : null}
                  {row.agent_response || row.draft_summary ? (
                    <details className="plan-execute-history__response">
                      <summary>에이전트 응답</summary>
                      <PlanAgentResponse text={row.agent_response || row.draft_summary || ""} />
                    </details>
                  ) : null}
                </li>
                );
              })}
          </ul>
        </details>
      ) : null}

      {error ? <p className="plan-execute-panel__error">{error}</p> : null}
    </div>
  );
}
