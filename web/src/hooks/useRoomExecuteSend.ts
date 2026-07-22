import {
  useCallback,
  type Dispatch,
  type MutableRefObject,
  type SetStateAction,
} from "react";
import { cancelRoomRun, runRoom } from "../api/client";
import type { PendingFile } from "../components/ChatComposer";
import type { useLocale } from "../i18n/useLocale";
import { registerRoomEventHandler } from "../run/roomReconnectRegistry";
import {
  finalizeCancelledTyping,
  finishSessionRun,
  resetTurnRun,
  resolveRunSessionKey,
} from "../run/runSessionRegistry";
import {
  capabilitiesForApi,
  type AgentCapabilitiesMap,
} from "../utils/agentCapabilities";
import {
  clearStoredAgentThreadBindings,
  getStoredAgentThreadBindings,
  type AgentThreadBindings,
} from "../utils/agentThreadBindings";
import { sortAgentIds } from "../utils/agentOrder";
import type { AgentPermissions } from "../utils/agentPermissions";
import { sendReceiptLabel } from "../utils/sendReceipt";
import { topicAsUserMessage } from "../utils/transcript";
import {
  resolveTurnSend,
  turnProfileForRoomPreset,
  type ComposerTurnProfile,
} from "../utils/turnProfile";
import {
  IMPLICIT_ROOM_PRESET,
  TOPIC_ONLY_COMPOSER,
} from "../utils/roomComposerPrefs";
import { writePendingRoomModels } from "../utils/modelSlash";
import { attachmentSendTopic } from "../utils/roomSessionMessages";
import type { ConsensusDryRunProposal } from "../components/ConsensusDryRunGateBar";
import {
  classifySendFailure,
  type RecoveryFailure,
} from "../utils/recoveryItems";
import {
  CUSTOM_WORKSPACE_ID,
  getStoredSessionTemplate,
} from "../utils/sessionSetup";
import {
  createRoomRunEventHandler,
  type RoomRunScope,
} from "./useRoomSseHandler";

type MacNotificationPayload = {
  title: string;
  body?: string;
};

export type ExecuteSendFn = (
  msgText: string,
  filesToSend: PendingFile[],
  permissions: AgentPermissions,
) => Promise<void>;

export type RoomExecuteSendOptions = {
  sessionId: string | null;
  selected: string[];
  runBusy: boolean;
  running: boolean;
  synthesizing: boolean;
  composerModeVariant: "discuss" | "plan" | "consensus";
  turnProfile: ComposerTurnProfile;
  roomPreset: string | null;
  researchMode: boolean;
  workspaceId: string;
  workspacePath: string | null;
  agentCapabilities: AgentCapabilitiesMap;
  bootstrapAgentThreadBindings?: AgentThreadBindings | null;
  bootstrapSessionTemplate?: string | null;
  locale: ReturnType<typeof useLocale>["locale"];
  localeMsg: ReturnType<typeof useLocale>["msg"];
  onSessionChange: (sessionId: string) => void | Promise<void>;
  onSessionBind?: (sessionId: string) => void | Promise<void>;
  onSessionMetaRefresh?: (sessionId: string) => void | Promise<void>;
  onBootstrapMissionTemplateApplied?: () => void;
  refreshSessionMeta: () => void | Promise<void>;
  persistPendingSessionRoomModels: (sessionId: string) => void | Promise<void>;
  clearRunWatchdog: () => void;
  scheduleLongRunHint: () => void;
  clearLongRunHint: () => void;
  openPlanTab: () => void;
  notifyConsensusSync: (proposal: ConsensusDryRunProposal) => void;
  notifyConsensusFailure: (excerpt?: string, message?: string) => void;
  pushMacNotification: (payload: MacNotificationPayload) => void;
  refreshInboxPending: () => void | Promise<void>;
  openHumanInbox: () => void;
  openWorkTab: () => void;
  activeSessionIdRef: MutableRefObject<string | null>;
  navigatedToSessionRef: MutableRefObject<boolean>;
  pendingMissionTemplateRef: MutableRefObject<string | null>;
  pendingSessionRoomModelsRef: MutableRefObject<string[] | null>;
  runAbortRef: MutableRefObject<AbortController | null>;
  sendReceiptTimerRef: MutableRefObject<number | null>;
  lastPlainSendTextRef: MutableRefObject<string | null>;
  setPendingFiles: (files: PendingFile[]) => void;
  setLiveRunSessionKey: (id: string) => void;
  setRecoveryFailure: (
    value:
      | RecoveryFailure
      | null
      | ((prev: RecoveryFailure | null) => RecoveryFailure | null),
  ) => void;
  setRunLockStuck: (value: boolean) => void;
  setClarifierQuestions: (value: string[] | null) => void;
  setClarifierInterview: (
    value: {
      questions?: { id?: string; category?: string; prompt?: string }[];
      plan_mode?: boolean;
    } | null,
  ) => void;
  setDiscussPaused: (value: boolean) => void;
  setInboxReloadKey: (value: number | ((prev: number) => number)) => void;
  setWorkHookAlert: (
    value: {
      event: string;
      body: string;
      blocked: boolean;
    } | null,
  ) => void;
  setConsensusProposal: Dispatch<
    SetStateAction<ConsensusDryRunProposal | null>
  >;
  setSendReceipt: (value: string | null) => void;
  setSendReceiptRaw: (value: string | undefined) => void;
};

export function useRoomExecuteSend(options: RoomExecuteSendOptions): {
  executeSend: ExecuteSendFn;
} {
  const {
    sessionId,
    selected,
    runBusy,
    running,
    synthesizing,
    composerModeVariant,
    turnProfile,
    roomPreset,
    researchMode,
    workspaceId,
    workspacePath,
    agentCapabilities,
    bootstrapAgentThreadBindings,
    bootstrapSessionTemplate,
    locale,
    localeMsg,
    onSessionChange,
    onSessionBind,
    onSessionMetaRefresh,
    onBootstrapMissionTemplateApplied,
    refreshSessionMeta,
    persistPendingSessionRoomModels,
    clearRunWatchdog,
    scheduleLongRunHint,
    clearLongRunHint,
    openPlanTab,
    notifyConsensusSync,
    notifyConsensusFailure,
    pushMacNotification,
    refreshInboxPending,
    openHumanInbox,
    openWorkTab,
    activeSessionIdRef,
    navigatedToSessionRef,
    pendingMissionTemplateRef,
    pendingSessionRoomModelsRef,
    runAbortRef,
    sendReceiptTimerRef,
    lastPlainSendTextRef,
    setPendingFiles,
    setLiveRunSessionKey,
    setRecoveryFailure,
    setRunLockStuck,
    setClarifierQuestions,
    setClarifierInterview,
    setDiscussPaused,
    setInboxReloadKey,
    setWorkHookAlert,
    setConsensusProposal,
    setSendReceipt,
    setSendReceiptRaw,
  } = options;

  const executeSend = useCallback<ExecuteSendFn>(
    async (msgText, filesToSend, permissions) => {
      if (runBusy || running || synthesizing) return;
      const effectiveProfile: ComposerTurnProfile = turnProfileForRoomPreset(
        roomPreset ?? IMPLICIT_ROOM_PRESET,
      );
      const {
        agents,
        agentRounds,
        reviewMode: useReviewMode,
        consensusMode: useConsensusMode,
      } = resolveTurnSend(effectiveProfile, selected);
      if (agents.length === 0) return;

      const pinnedRoomModels = !sessionId
        ? (pendingSessionRoomModelsRef.current ?? sortAgentIds(selected))
        : undefined;

      const sendText =
        msgText.trim() ||
        (filesToSend.length ? attachmentSendTopic(filesToSend) : "");
      if (!sendText) return;

      const attachmentNames = filesToSend.map((p) => p.file.name);
      const displayBody = msgText.trim();
      if (displayBody && filesToSend.length === 0) {
        lastPlainSendTextRef.current = displayBody;
      }
      setPendingFiles([]);

      const threadBindings = !sessionId
        ? (bootstrapAgentThreadBindings ??
          getStoredAgentThreadBindings() ??
          undefined)
        : undefined;
      const sessionTemplate = sessionId
        ? undefined
        : (bootstrapSessionTemplate ?? getStoredSessionTemplate());

      const runKey = resolveRunSessionKey(
        sessionId,
        activeSessionIdRef.current,
      );
      const userMsg = topicAsUserMessage(
        displayBody,
        attachmentNames.length ? attachmentNames : undefined,
      );
      resetTurnRun(runKey, userMsg);
      clearRunWatchdog();
      scheduleLongRunHint();
      setRunLockStuck(false);
      setRecoveryFailure(null);
      setClarifierQuestions(null);
      const runScope: RoomRunScope = {
        runKey,
        activeSessionId: sessionId,
        userStopped: false,
        runFailed: false,
        lastSendReceipt: undefined,
      };
      runAbortRef.current?.abort();
      const runAbort = new AbortController();
      runAbortRef.current = runAbort;

      const onRoomEvent = createRoomRunEventHandler(runScope, {
        sessionId,
        profile: effectiveProfile,
        selected,
        localeMsg,
        activeSessionIdRef,
        navigatedToSessionRef,
        pendingMissionTemplateRef,
        onSessionBind,
        onSessionChange,
        onSessionMetaRefresh,
        onBootstrapMissionTemplateApplied,
        setLiveRunSessionKey,
        persistPendingSessionRoomModels,
        openPlanTab,
        setRecoveryFailure,
        setRunLockStuck,
        setClarifierQuestions,
        setClarifierInterview,
        setDiscussPaused,
        setInboxReloadKey,
        setWorkHookAlert,
        setConsensusProposal,
        notifyConsensusSync,
        notifyConsensusFailure,
        pushMacNotification,
        refreshSessionMeta,
        refreshInboxPending,
        openHumanInbox,
        openWorkTab,
      });

      const onRoomEventWithRegistry = (ev: Record<string, unknown>) => {
        const evType = String(ev.type ?? "");
        if (evType === "start" && typeof ev.session_id === "string") {
          registerRoomEventHandler(ev.session_id, onRoomEventWithRegistry);
        }
        onRoomEvent(ev);
      };
      if (sessionId) {
        registerRoomEventHandler(sessionId, onRoomEventWithRegistry);
      }

      try {
        await runRoom(sendText, agents, onRoomEventWithRegistry, {
          sessionId: sessionId ?? undefined,
          files: filesToSend.map((p) => p.file),
          agentRounds,
          permissions,
          reviewMode: useReviewMode,
          consensusMode: useConsensusMode,
          turnProfile: TOPIC_ONLY_COMPOSER ? undefined : effectiveProfile,
          researchMode,
          workspaceId: sessionId ? undefined : workspaceId,
          workspacePath:
            sessionId || workspaceId !== CUSTOM_WORKSPACE_ID
              ? undefined
              : (workspacePath ?? undefined),
          agentCapabilities: capabilitiesForApi(agentCapabilities),
          agentThreadBindings: threadBindings,
          sessionTemplate,
          roomPreset: TOPIC_ONLY_COMPOSER
            ? IMPLICIT_ROOM_PRESET
            : (roomPreset ?? undefined),
          roomModels: pinnedRoomModels,
          signal: runAbort.signal,
        });
        if (runScope.runFailed) {
          return;
        }
        if (!sessionId && pinnedRoomModels?.length) {
          pendingSessionRoomModelsRef.current = null;
          writePendingRoomModels(null);
        }
        if (!sessionId) {
          clearStoredAgentThreadBindings();
        }
        if (
          runScope.activeSessionId &&
          !navigatedToSessionRef.current &&
          !sessionId
        ) {
          activeSessionIdRef.current = runScope.activeSessionId;
          onSessionChange(runScope.activeSessionId);
        }
        if (
          runScope.lastSendReceipt === "plan_updated" &&
          (runScope.activeSessionId ?? sessionId)
        ) {
          openPlanTab();
        }
        setSendReceiptRaw(runScope.lastSendReceipt);
        setSendReceipt(
          sendReceiptLabel(
            runScope.lastSendReceipt,
            composerModeVariant === "plan",
            runScope.userStopped,
            locale,
          ),
        );
        if (sendReceiptTimerRef.current != null) {
          window.clearTimeout(sendReceiptTimerRef.current);
        }
        sendReceiptTimerRef.current = window.setTimeout(() => {
          setSendReceipt(null);
          sendReceiptTimerRef.current = null;
        }, 5000);
      } catch (e) {
        const msg = String(e);
        if (runAbort.signal.aborted || msg.includes("aborted")) {
          runScope.userStopped = true;
        } else if (runScope.runFailed) {
          // SSE handler already set recovery.
        } else {
          const detail = msg.replace(/^Error:\s*/, "");
          const classified = classifySendFailure(detail);
          setRecoveryFailure({
            source: classified.source,
            kind: classified.kind,
            message: detail,
            affectedAgentIds: classified.affectedAgentIds,
          });
          if (classified.kind === "run_lock") {
            setRunLockStuck(true);
          } else if (
            msg.includes("already in progress") ||
            msg.includes("not ready")
          ) {
            setRunLockStuck(msg.includes("already in progress"));
          }
        }
      } finally {
        if (runAbortRef.current === runAbort) {
          runAbortRef.current = null;
        }
        if (runAbort.signal.aborted) {
          runScope.userStopped = true;
          void cancelRoomRun(
            runScope.activeSessionId ?? sessionId ?? undefined,
          ).catch(() => {});
        }
        if (runScope.userStopped) {
          finalizeCancelledTyping(runScope.runKey);
        }
        clearRunWatchdog();
        clearLongRunHint();
        finishSessionRun(
          runScope.runKey,
          runScope.activeSessionId ?? undefined,
        );
        const boundSid = runScope.activeSessionId ?? sessionId;
        if (boundSid && onSessionMetaRefresh && !runScope.runFailed) {
          void onSessionMetaRefresh(boundSid);
        }
        navigatedToSessionRef.current = false;
      }
    },
    [
      selected,
      sessionId,
      onSessionChange,
      onSessionBind,
      onSessionMetaRefresh,
      composerModeVariant,
      turnProfile,
      researchMode,
      workspaceId,
      workspacePath,
      agentCapabilities,
      bootstrapAgentThreadBindings,
      bootstrapSessionTemplate,
      refreshSessionMeta,
      persistPendingSessionRoomModels,
      runBusy,
      running,
      synthesizing,
      roomPreset,
      locale,
      localeMsg,
      clearRunWatchdog,
      scheduleLongRunHint,
      clearLongRunHint,
      openPlanTab,
      notifyConsensusSync,
      notifyConsensusFailure,
      pushMacNotification,
      refreshInboxPending,
      openHumanInbox,
      openWorkTab,
      onBootstrapMissionTemplateApplied,
      activeSessionIdRef,
      navigatedToSessionRef,
      pendingMissionTemplateRef,
      pendingSessionRoomModelsRef,
      runAbortRef,
      sendReceiptTimerRef,
      lastPlainSendTextRef,
      setPendingFiles,
      setLiveRunSessionKey,
      setRecoveryFailure,
      setRunLockStuck,
      setClarifierQuestions,
      setClarifierInterview,
      setDiscussPaused,
      setInboxReloadKey,
      setWorkHookAlert,
      setConsensusProposal,
      setSendReceipt,
      setSendReceiptRaw,
    ],
  );

  return { executeSend };
}
