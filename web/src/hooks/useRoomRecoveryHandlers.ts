import { useCallback } from "react";
import {
  postMissionDiscussRecovery,
  reconnectClaudeAuth,
  reconnectCursorBridge,
  reconnectKimiWorkBridge,
  releaseRoomRunLock,
  retryAgents,
} from "../api/client";
import { fetchReadiness, type ReadinessResponse } from "../api/client";
import {
  clearBackgroundRun,
  markBackgroundRun,
} from "../run/runSessionRegistry";
import { dispatchNotification } from "../utils/pushNotification";
import { notifyDesktop } from "../utils/desktopNotify";
import { focusComposerInput } from "../utils/taskBarCopy";
import {
  recoveryItemKey,
  type RecoveryResolutionEvent,
  type RecoveryRetryActionId,
} from "../utils/recoveryLifecycle";
import {
  type RecoveryActionId,
  type RecoveryItem,
} from "../utils/recoveryItems";
import type { RecoveryFailure } from "../utils/recoveryItems";
import type { SlashCommandRecord } from "../api/client";
import type { MutableRefObject, Dispatch, SetStateAction } from "react";

export type RoomRecoveryNotificationsOptions = {
  sessionId: string | null;
  pushMacNotification: (payload: { title: string; body?: string }) => void;
};

/** Recovery desktop/toast notifications — extracted from RoomChat (F9). */
export function useRoomRecoveryNotifications({
  sessionId,
  pushMacNotification,
}: RoomRecoveryNotificationsOptions) {
  const notifyRecoveryResolution = useCallback(
    (event: RecoveryResolutionEvent) => {
      const workRecovery =
        event.kind === "oracle_fail" || event.kind === "discuss_recovery";
      dispatchNotification(
        {
          tier: event.status === "resolved" ? "P1" : "P0",
          title:
            event.status === "resolved"
              ? "Recovery resolved"
              : "Recovery still blocked",
          body: event.message,
          sessionId: sessionId ?? undefined,
          kind:
            event.status === "resolved"
              ? workRecovery
                ? "recovery_resolved_work"
                : "recovery_resolved"
              : "recovery_still_blocked",
          entityId: event.key,
          toastAction:
            event.status === "resolved" && workRecovery
              ? { type: "composer", focus: "execute" }
              : undefined,
        },
        pushMacNotification,
        notifyDesktop,
      );
    },
    [pushMacNotification, sessionId],
  );

  const notifyRecoveryStarted = useCallback(
    (item: RecoveryItem, actionId: RecoveryActionId) => {
      dispatchNotification(
        {
          tier: "P2",
          title: "Recovery action started",
          body: `${item.title} · ${actionId}`,
          sessionId: sessionId ?? undefined,
          kind: "recovery_started",
          entityId: recoveryItemKey(item),
        },
        pushMacNotification,
        notifyDesktop,
      );
    },
    [pushMacNotification, sessionId],
  );

  return { notifyRecoveryResolution, notifyRecoveryStarted };
}

export type RoomRecoveryActionsOptions = {
  sessionId: string | null;
  activeSessionIdRef: MutableRefObject<string | null>;
  lastPlainSendTextRef: MutableRefObject<string | null>;
  slashCommands: SlashCommandRecord[];
  onOpenSettings?: () => void;
  onRefreshHealth?: () => void | Promise<void>;
  onSessionChange: (sessionId: string) => void | Promise<void>;
  refreshSessionMeta: () => void;
  setReadiness: (value: ReadinessResponse | null) => void;
  setReleasingLock: (value: boolean) => void;
  setRunLockStuck: (value: boolean) => void;
  setRecoveryFailure: (failure: RecoveryFailure | null) => void;
  setDiscussRecoveryBusy: (value: boolean) => void;
  setRecoveryBusyAction: (actionId: RecoveryActionId | null) => void;
  setText: (text: string) => void;
  setWorkFocus: Dispatch<SetStateAction<import("../components/WorkToolPanel").WorkFocusTarget | null>>;
  beginRecoveryAttempt: (
    item: RecoveryItem,
    actionId: RecoveryActionId,
    hasLastMessage: boolean,
  ) => string | null;
  finishRecoveryAction: (attemptId: string | null) => void;
  executeSlashCommand: (cmd: SlashCommandRecord, arg: string) => Promise<void>;
  notifyRecoveryStarted: (item: RecoveryItem, actionId: RecoveryActionId) => void;
  openWorkTab: () => void;
  openHumanInbox: () => void;
  openTranscriptTab: () => void;
};

/** Recovery action dispatch — extracted from RoomChat (F9). */
export function useRoomRecoveryActions({
  sessionId,
  activeSessionIdRef,
  lastPlainSendTextRef,
  slashCommands,
  onOpenSettings,
  onRefreshHealth,
  onSessionChange,
  refreshSessionMeta,
  setReadiness,
  setReleasingLock,
  setRunLockStuck,
  setRecoveryFailure,
  setDiscussRecoveryBusy,
  setRecoveryBusyAction,
  setText,
  setWorkFocus,
  beginRecoveryAttempt,
  finishRecoveryAction,
  executeSlashCommand,
  notifyRecoveryStarted,
  openWorkTab,
  openHumanInbox,
  openTranscriptTab,
}: RoomRecoveryActionsOptions) {
  const handleReleaseRunLock = useCallback(async () => {
    setReleasingLock(true);
    try {
      await releaseRoomRunLock();
      setRunLockStuck(false);
      setRecoveryFailure(null);
    } catch (e) {
      setRecoveryFailure({ source: "command", message: String(e) });
    } finally {
      setReleasingLock(false);
    }
  }, [setRecoveryFailure, setReleasingLock, setRunLockStuck]);

  const handleRetryFailedAgents = useCallback(async () => {
    const sid = sessionId ?? activeSessionIdRef.current;
    if (!sid) return;
    markBackgroundRun(sid, {
      runKind: "retry",
      label: "Retry failed agents",
    });
    try {
      await retryAgents(sid);
      await onSessionChange(sid);
      setRecoveryFailure(null);
    } finally {
      clearBackgroundRun(sid, "retry");
    }
  }, [onSessionChange, sessionId, activeSessionIdRef, setRecoveryFailure]);

  const handleDiscussRecoveryRun = useCallback(async () => {
    if (!sessionId) return;
    setDiscussRecoveryBusy(true);
    try {
      await postMissionDiscussRecovery(sessionId);
      refreshSessionMeta();
    } finally {
      setDiscussRecoveryBusy(false);
    }
  }, [refreshSessionMeta, sessionId, setDiscussRecoveryBusy]);

  const refreshRecoveryReadiness = useCallback(async () => {
    await onRefreshHealth?.();
    if (sessionId) {
      const next = await fetchReadiness(sessionId, true);
      setReadiness(next);
    }
    refreshSessionMeta();
  }, [onRefreshHealth, refreshSessionMeta, sessionId, setReadiness]);

  const handleRecoveryAction = useCallback(
    async (actionId: RecoveryActionId, item: RecoveryItem) => {
      const tracksResolution =
        actionId !== "open_settings" &&
        actionId !== "open_work" &&
        actionId !== "open_inbox";
      let attemptId: string | null = null;
      if (tracksResolution) {
        attemptId = beginRecoveryAttempt(
          item,
          actionId,
          Boolean(lastPlainSendTextRef.current),
        );
        notifyRecoveryStarted(item, actionId);
      }
      setRecoveryBusyAction(actionId);
      try {
        switch (actionId) {
          case "open_settings":
            onOpenSettings?.();
            return;
          case "refresh_health":
            await refreshRecoveryReadiness();
            return;
          case "reconnect_cursor":
            await reconnectCursorBridge();
            await refreshRecoveryReadiness();
            return;
          case "reconnect_claude": {
            const loginCmd = slashCommands.find(
              (candidate) => candidate.id === "login",
            );
            if (loginCmd) {
              await executeSlashCommand(loginCmd, "claude");
              return;
            }
            await reconnectClaudeAuth();
            await refreshRecoveryReadiness();
            return;
          }
          case "reconnect_codex": {
            const loginCmd = slashCommands.find(
              (candidate) => candidate.id === "login",
            );
            if (loginCmd) {
              await executeSlashCommand(loginCmd, "codex");
              return;
            }
            onOpenSettings?.();
            return;
          }
          case "reconnect_kimi_work":
            await reconnectKimiWorkBridge();
            await refreshRecoveryReadiness();
            return;
          case "release_lock":
            await handleReleaseRunLock();
            return;
          case "retry_failed_agents":
            await handleRetryFailedAgents();
            return;
          case "open_work":
            openWorkTab();
            setWorkFocus("execute");
            return;
          case "open_inbox":
            openHumanInbox();
            return;
          case "run_discuss_recovery":
            await handleDiscussRecoveryRun();
            return;
        }
      } catch (e) {
        setRecoveryFailure({
          source: "command",
          message: e instanceof Error ? e.message : String(e),
        });
      } finally {
        finishRecoveryAction(attemptId);
      }
    },
    [
      beginRecoveryAttempt,
      executeSlashCommand,
      finishRecoveryAction,
      handleDiscussRecoveryRun,
      handleReleaseRunLock,
      handleRetryFailedAgents,
      lastPlainSendTextRef,
      notifyRecoveryStarted,
      onOpenSettings,
      openHumanInbox,
      openWorkTab,
      refreshRecoveryReadiness,
      setRecoveryBusyAction,
      setRecoveryFailure,
      setWorkFocus,
      slashCommands,
    ],
  );

  const handleRecoveryRetryAction = useCallback(
    (actionId: RecoveryRetryActionId, event: RecoveryResolutionEvent): void => {
      if (event.kind === "oracle_fail" || event.kind === "discuss_recovery") {
        openWorkTab();
        setWorkFocus("execute");
        return;
      }
      openTranscriptTab();
      if (actionId === "restore_last_message" && lastPlainSendTextRef.current) {
        setText(lastPlainSendTextRef.current);
      }
      focusComposerInput();
    },
    [lastPlainSendTextRef, openTranscriptTab, openWorkTab, setText, setWorkFocus],
  );

  return {
    handleReleaseRunLock,
    handleRetryFailedAgents,
    handleDiscussRecoveryRun,
    refreshRecoveryReadiness,
    handleRecoveryAction,
    handleRecoveryRetryAction,
  };
}
