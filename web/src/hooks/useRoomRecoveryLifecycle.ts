import { useCallback, useEffect, useMemo, useState } from "react";
import type { AgentHealthRow, PlanExecutionRecord } from "../api/client";
import type { ReadinessResponse } from "../api/client";
import {
  buildRecoveryItems,
  type RecoveryActionId,
  type RecoveryFailure,
  type RecoveryItem,
} from "../utils/recoveryItems";
import {
  buildRecoveryLifecycleView,
  createRecoveryAttempt,
  resolveRecoveryAttempt,
  type RecoveryAttempt,
  type RecoveryResolutionEvent,
} from "../utils/recoveryLifecycle";

export type DiscussRecoveryState = {
  pending?: boolean;
  reason?: string | null;
  action_index?: number | null;
};

export type UseRoomRecoveryLifecycleArgs = {
  sessionId: string | null;
  apiOk: boolean;
  healthAgents: AgentHealthRow[];
  readiness: ReadinessResponse | null;
  selectedAgentIds: string[];
  runLockStuck: boolean;
  discussRecovery: DiscussRecoveryState | null;
  executeError: string | null | undefined;
  planExecutions: readonly PlanExecutionRecord[];
  composerSendLocked: boolean;
  onResolutionNotify: (event: RecoveryResolutionEvent) => void;
};

/** Phase 1c (F6): recovery attempt tracking + lifecycle view — extracted from RoomChat. */
export function useRoomRecoveryLifecycle({
  sessionId,
  apiOk,
  healthAgents,
  readiness,
  selectedAgentIds,
  runLockStuck,
  discussRecovery,
  executeError,
  planExecutions,
  composerSendLocked,
  onResolutionNotify,
}: UseRoomRecoveryLifecycleArgs) {
  const [recoveryFailure, setRecoveryFailure] =
    useState<RecoveryFailure | null>(null);
  const [pendingRecoveryAttempt, setPendingRecoveryAttempt] =
    useState<RecoveryAttempt | null>(null);
  const [recoveryCheckAttemptId, setRecoveryCheckAttemptId] = useState<
    string | null
  >(null);
  const [recoveryResolutionEvents, setRecoveryResolutionEvents] = useState<
    RecoveryResolutionEvent[]
  >([]);
  const [discussRecoveryBusy, setDiscussRecoveryBusy] = useState(false);
  const [recoveryBusyAction, setRecoveryBusyAction] =
    useState<RecoveryActionId | null>(null);
  const [recoveryDismissedSig, setRecoveryDismissedSig] = useState<
    string | null
  >(null);

  const activeRecoveryFailure = useMemo<RecoveryFailure | null>(() => {
    if (recoveryFailure) return recoveryFailure;
    if (!executeError) return null;
    return { source: "execute", message: executeError };
  }, [executeError, recoveryFailure]);

  const recoveryItems = useMemo(
    () =>
      buildRecoveryItems({
        apiOk,
        agents: healthAgents,
        readiness,
        failure: activeRecoveryFailure,
        selectedAgentIds,
        runLockStuck,
        discussRecovery,
        executions: planExecutions,
      }),
    [
      activeRecoveryFailure,
      apiOk,
      discussRecovery,
      healthAgents,
      planExecutions,
      readiness,
      runLockStuck,
      selectedAgentIds,
    ],
  );

  useEffect(() => {
    if (
      !pendingRecoveryAttempt ||
      recoveryCheckAttemptId !== pendingRecoveryAttempt.id
    ) {
      return;
    }
    const event = resolveRecoveryAttempt({
      attempt: pendingRecoveryAttempt,
      currentItems: recoveryItems,
    });
    setRecoveryResolutionEvents((current) => [event, ...current].slice(0, 3));
    window.setTimeout(() => {
      setRecoveryResolutionEvents((current) =>
        current.filter((candidate) => candidate.id !== event.id),
      );
    }, 3000);
    setPendingRecoveryAttempt(null);
    setRecoveryCheckAttemptId(null);
    onResolutionNotify(event);
  }, [
    onResolutionNotify,
    recoveryCheckAttemptId,
    pendingRecoveryAttempt,
    recoveryItems,
  ]);

  const recoveryLifecycleView = useMemo(
    () =>
      buildRecoveryLifecycleView({
        activeItems: recoveryItems,
        resolvedEvents: recoveryResolutionEvents,
        composerSendLocked,
      }),
    [composerSendLocked, recoveryItems, recoveryResolutionEvents],
  );

  const recoverySignature = useMemo(
    () =>
      [
        ...recoveryLifecycleView.activeItems.map(
          (item) => `${item.kind}:${item.severity}`,
        ),
        ...recoveryLifecycleView.resolvedEvents.map((event) => `r:${event.id}`),
      ].join("|"),
    [recoveryLifecycleView.activeItems, recoveryLifecycleView.resolvedEvents],
  );

  const recoveryVisible =
    recoverySignature.length > 0 && recoveryDismissedSig !== recoverySignature;

  const beginRecoveryAttempt = useCallback(
    (
      item: RecoveryItem,
      actionId: RecoveryActionId,
      canRestoreLastMessage: boolean,
    ): string => {
      const attempt = createRecoveryAttempt({
        item,
        actionId,
        canRestoreLastMessage,
      });
      setPendingRecoveryAttempt(attempt);
      setRecoveryCheckAttemptId(null);
      return attempt.id;
    },
    [],
  );

  const finishRecoveryAction = useCallback((attemptId: string | null) => {
    setRecoveryBusyAction(null);
    if (attemptId) {
      window.setTimeout(() => {
        setRecoveryCheckAttemptId(attemptId);
      }, 250);
    }
  }, []);

  useEffect(() => {
    if (sessionId !== null) return;
    setRecoveryFailure(null);
  }, [sessionId]);

  return {
    recoveryFailure,
    setRecoveryFailure,
    recoveryItems,
    recoveryLifecycleView,
    recoverySignature,
    recoveryVisible,
    recoveryDismissedSig,
    setRecoveryDismissedSig,
    discussRecoveryBusy,
    setDiscussRecoveryBusy,
    recoveryBusyAction,
    setRecoveryBusyAction,
    beginRecoveryAttempt,
    finishRecoveryAction,
  };
}

export function discussRecoveryFromMissionLoop(
  missionLoop: unknown,
): DiscussRecoveryState | null {
  const ml = missionLoop as
    | { discuss_recovery?: DiscussRecoveryState }
    | undefined;
  return ml?.discuss_recovery ?? null;
}
