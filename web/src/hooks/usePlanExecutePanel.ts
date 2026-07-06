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
  type MergeChecksPayload,
} from "../api/client";
import {
  actionKey,
  diffHunks,
  executePermissions,
  linkedTaskForAction,
  openBlockObjectionsForAction,
  parseActionKey,
  EXECUTION_HISTORY_LIMIT,
} from "../components/PlanExecutePanelSupport";
import { executionApprovalGate } from "../utils/executeApprovalGate";
import { formatPlanExecuteError } from "../utils/planExecuteErrors";
import {
  buildPlanTodoRows,
  planTodoProgress,
  resolvePlanDiffRollup,
} from "../utils/planTodoView";
import { findActiveExecution } from "../utils/planExecuteWorktree";
import {
  resolveExecutionAction,
  type StoredPlanAction,
} from "../utils/planExecuteHistory";

type UsePlanExecutePanelArgs = {
  sessionId: string;
  run?: Record<string, unknown>;
  linkedTasks?: RoomTask[];
  disabled?: boolean;
  mergeChecks?: MergeChecksPayload | null;
  onUpdated: () => void;
};

export function usePlanExecutePanel({
  sessionId,
  run,
  linkedTasks,
  disabled,
  mergeChecks = null,
  onUpdated,
}: UsePlanExecutePanelArgs) {
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

  const handleDryRun = useCallback(async () => {
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
  }, [activePending, onUpdated, selectedKey, sessionId]);

  const handleApprovePlanSnapshot = useCallback(async () => {
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
  }, [handleDryRun, planSnapshot?.id, sessionId]);

  const handleRejectPlanSnapshot = useCallback(async () => {
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
  }, [planSnapshot?.id, sessionId]);

  const handleResolve = useCallback(
    async (vote: "approve" | "reject") => {
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
    },
    [activePending?.id, onUpdated, refreshActions, sessionId],
  );

  const handleRevisePending = useCallback(async () => {
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
  }, [
    activePending?.id,
    onUpdated,
    pendingDiffHunks,
    refreshActions,
    reviseComment,
    reviseHunkId,
    sessionId,
  ]);

  const handleMergeAbort = useCallback(async () => {
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
  }, [activePending?.id, onUpdated, refreshActions, sessionId]);

  const handleMergeConfirm = useCallback(async () => {
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
  }, [activePending?.id, onUpdated, refreshActions, sessionId]);

  const handleReverify = useCallback(
    async (executionId: string) => {
      setBusy(true);
      setError(null);
      try {
        await reverifyPlanExecution(
          sessionId,
          executionId,
          executePermissions(),
        );
        onUpdated();
        await refreshActions();
      } catch (e) {
        setError(formatPlanExecuteError(e));
      } finally {
        setBusy(false);
      }
    },
    [onUpdated, refreshActions, sessionId],
  );

  const handleIsolationOverride = useCallback(
    async (executionId?: string) => {
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
    },
    [isolationBlock?.executionId, onUpdated, sessionId],
  );

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

  return {
    recommended,
    loadingActions,
    planSnapshot,
    selectedKey,
    setSelectedKey,
    isolationBlock,
    setIsolationBlock,
    objectionBlock,
    busy,
    error,
    reviseComment,
    setReviseComment,
    reviseHunkId,
    setReviseHunkId,
    reviseError,
    revising,
    artifactsReviewConfirmed,
    setArtifactsReviewConfirmed,
    storedActions,
    historyRows,
    historyVisible,
    activePending,
    pendingAction,
    approvalGate,
    approveBlocked,
    mergeBlockTitle,
    pendingDiffHunks,
    hasDryRun,
    hasNowSection,
    nowHasOnlyGates,
    selectedOpenBlocks,
    linkedForSelected,
    linkedForPending,
    executeWorkspace,
    todoRows,
    todoProgress,
    todoDiffRollup,
    actionDisabled,
    handleDryRun,
    handleApprovePlanSnapshot,
    handleRejectPlanSnapshot,
    handleResolve,
    handleRevisePending,
    handleMergeAbort,
    handleMergeConfirm,
    handleReverify,
    handleIsolationOverride,
  };
}
