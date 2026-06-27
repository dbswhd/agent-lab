import { useCallback, useEffect, useMemo, useState } from "react";
import {
  markBackgroundRun,
  clearBackgroundRun,
} from "../run/runSessionRegistry";
import {
  fetchPlanActions,
  PlanExecuteDryRunError,
  resolvePlanExecution,
  runPlanDryRun,
  type PlanActionItem,
  type PlanExecutionRecord,
  type RoomObjection,
} from "../api/client";
import { fullAgentPermissions } from "../utils/agentPermissions";
import { executionApprovalGate } from "../utils/executeApprovalGate";
import { formatPlanExecuteError } from "../utils/planExecuteErrors";
import {
  executionContextFields,
  executionHistoryBadge,
  executionHistoryTitle,
  resolveExecutionAction,
  type StoredPlanAction,
} from "../utils/planExecuteHistory";
import {
  executionApproveLabel,
  findActiveExecution,
  isActiveExecution,
} from "../utils/planExecuteWorktree";

function actionKey(
  item: Pick<PlanActionItem, "kind" | "index" | "recommended">,
): string {
  const kind = item.kind ?? (item.recommended ? "now" : "roadmap");
  return `${kind}:${item.index}`;
}

export function parsePlanActionKey(
  key: string,
): { kind: string; index: number } | null {
  const sep = key.indexOf(":");
  if (sep <= 0) return null;
  const kind = key.slice(0, sep);
  const index = Number(key.slice(sep + 1));
  if (!Number.isFinite(index) || index < 1) return null;
  return { kind, index };
}

export function reviewRequiredLabel(
  row: PlanExecutionRecord | null | undefined,
): string {
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
  if (pdfPath) return `PDF 확인 후 승인 · ${pdfPath}`;
  if (pageBit) return `PDF 확인 후 승인 (${pageBit})`;
  return "PDF 확인 후 승인";
}

export function executionStatusLabel(
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
    case "superseded":
      return "재작업으로 대체됨";
    case "merged":
      return "main에 병합됨";
    case "merge_conflict":
      return "merge 충돌";
    case "failed":
      return "실패";
    default:
      return status || "—";
  }
}

export function findPendingExecution(
  executions: PlanExecutionRecord[] | undefined,
): PlanExecutionRecord | null {
  return findActiveExecution(executions);
}

export { findActiveExecution, isActiveExecution };

type Options = {
  sessionId: string | null;
  run?: Record<string, unknown>;
  onUpdated?: () => void;
};

export function usePlanExecute({ sessionId, run, onUpdated }: Options) {
  const [recommended, setRecommended] = useState<PlanActionItem | null>(null);
  const [nowItems, setNowItems] = useState<PlanActionItem[]>([]);
  const [roadmap, setRoadmap] = useState<PlanActionItem[]>([]);
  const [loadingActions, setLoadingActions] = useState(false);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [localPending, setLocalPending] = useState<PlanExecutionRecord | null>(
    null,
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [openObjectionBlock, setOpenObjectionBlock] = useState<{
    message: string;
    objections: RoomObjection[];
  } | null>(null);

  const executions = useMemo(
    () => (run?.executions as PlanExecutionRecord[] | undefined) ?? [],
    [run],
  );

  const storedActions = useMemo(
    () => (run?.actions as StoredPlanAction[] | undefined) ?? [],
    [run],
  );

  const pendingFromRun = useMemo(
    () => findPendingExecution(executions),
    [executions],
  );

  const activePending = localPending ?? pendingFromRun;
  const pendingAction = activePending
    ? resolveExecutionAction(activePending, storedActions)
    : null;

  const lastPlanUpdateTs = useMemo(() => {
    const lpu = run?.last_plan_update as
      | { completed_at?: string; ts?: string }
      | undefined;
    return lpu?.completed_at || lpu?.ts || null;
  }, [run?.last_plan_update]);

  const refreshActions = useCallback(async () => {
    if (!sessionId) return;
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

  useEffect(() => {
    void refreshActions();
  }, [refreshActions, lastPlanUpdateTs, sessionId]);

  useEffect(() => {
    setLocalPending(null);
    setOpenObjectionBlock(null);
  }, [sessionId]);

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

  const selectedAction = useMemo(() => {
    if (!selectedKey) return null;
    return (
      executableItems.find((item) => actionKey(item) === selectedKey) ?? null
    );
  }, [executableItems, selectedKey]);

  const canDryRun = Boolean(
    sessionId && selectedKey && !activePending && executableItems.length > 0,
  );

  const dryRun = useCallback(
    async (overrideKey?: string | null) => {
      const key = overrideKey ?? selectedKey;
      if (!sessionId || key == null || activePending) return false;
      const parsed = parsePlanActionKey(key);
      if (!parsed) return false;
      const executeLabel = `Execute action #${parsed.index}`;
      setBusy(true);
      setError(null);
      setOpenObjectionBlock(null);
      markBackgroundRun(sessionId, { runKind: "execute", label: executeLabel });
      try {
        const res = await runPlanDryRun(sessionId, {
          actionIndex: parsed.index,
          actionKind: parsed.kind,
          permissions: fullAgentPermissions(),
        });
        setLocalPending(res.execution);
        onUpdated?.();
        return true;
      } catch (e) {
        if (
          e instanceof PlanExecuteDryRunError &&
          e.code === "open_objection" &&
          e.objections?.length
        ) {
          setOpenObjectionBlock({
            message: e.message,
            objections: e.objections,
          });
          setError(null);
        } else {
          setError(formatPlanExecuteError(e));
        }
        return false;
      } finally {
        setBusy(false);
        clearBackgroundRun(sessionId, "execute");
      }
    },
    [sessionId, selectedKey, activePending, onUpdated],
  );

  const resolve = useCallback(
    async (vote: "approve" | "reject") => {
      if (!sessionId || !activePending?.id) return false;
      if (vote === "approve") {
        const gate = executionApprovalGate(activePending);
        if (gate.blocked) {
          setError(gate.reason ?? "승인 불가");
          return false;
        }
      }
      setBusy(true);
      setError(null);
      try {
        await resolvePlanExecution(sessionId, {
          executionId: activePending.id,
          vote,
          permissions: fullAgentPermissions(),
        });
        setLocalPending(null);
        setSelectedKey(null);
        onUpdated?.();
        await refreshActions();
        return true;
      } catch (e) {
        setError(formatPlanExecuteError(e));
        return false;
      } finally {
        setBusy(false);
      }
    },
    [sessionId, activePending, onUpdated, refreshActions],
  );

  const pendingContext = activePending
    ? executionContextFields(activePending, pendingAction)
    : null;

  const approvalGate = executionApprovalGate(activePending);

  return {
    recommended,
    nowItems,
    roadmap,
    executions,
    executableItems,
    selectedKey,
    setSelectedKey,
    selectedAction,
    activePending,
    pendingAction,
    pendingContext,
    pendingTitle: activePending
      ? executionHistoryTitle(activePending, pendingAction)
      : null,
    pendingBadge: activePending ? executionHistoryBadge(activePending) : null,
    pendingStatusLabel: activePending
      ? executionStatusLabel(activePending.status, activePending)
      : null,
    approvalGate,
    canApprove: !approvalGate.blocked,
    approveLabel: executionApproveLabel(activePending),
    loadingActions,
    busy,
    error,
    openObjectionBlock,
    canDryRun,
    hasExecutableActions: executableItems.length > 0,
    dryRun,
    approve: () => resolve("approve"),
    reject: () => resolve("reject"),
    refreshActions,
    actionKey,
  };
}

export { actionKey };
