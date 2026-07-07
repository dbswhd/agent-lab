import { useCallback } from "react";
import {
  approvePlan,
  approveVerifiedLoop,
  rejectPlan,
  rejectVerifiedLoop,
  runSynthesizeOnly,
} from "../api/client";
import type { PlanApprovalMode, PlanRejectPayload } from "../components/PlanApprovalPanel";
import type { AgentPermissions } from "../utils/agentPermissions";
import { roomPermissions } from "../utils/agentPermissions";
import { updateSessionRun } from "../run/runSessionRegistry";
import type { ExecuteSendFn } from "./useRoomExecuteSend";
import type { usePlanExecute } from "./usePlanExecute";
import type { RecoveryFailure } from "../utils/recoveryItems";

type PlanExecuteSlice = Pick<
  ReturnType<typeof usePlanExecute>,
  "dryRun"
>;

export type RoomVerifiedHandlersOptions = {
  sessionId: string | null;
  showPlanApproval: boolean;
  verifiedEditGoal: string;
  verifiedEditCriteria: string;
  verifiedEditPromise: string;
  setVerifiedLoopBusy: (busy: boolean) => void;
  setVerifiedLoopError: (error: string | null) => void;
  refreshSessionMeta: () => void;
  planExecute: PlanExecuteSlice;
  executeSend: ExecuteSendFn;
  selected: string[];
  synthesizing: boolean;
  running: boolean;
  runBusy: boolean;
  messages: { length: number };
  onSessionChange: (sessionId: string) => void | Promise<void>;
  openPlanTab: () => void;
  clearRunWatchdog: () => void;
  setRecoveryFailure: (failure: RecoveryFailure | null) => void;
};

/** Verified loop approve/reject and plan synthesis — extracted from RoomChat (F9). */
export function useRoomVerifiedHandlers({
  sessionId,
  showPlanApproval,
  verifiedEditGoal,
  verifiedEditCriteria,
  verifiedEditPromise,
  setVerifiedLoopBusy,
  setVerifiedLoopError,
  refreshSessionMeta,
  planExecute,
  executeSend,
  selected,
  synthesizing,
  running,
  runBusy,
  messages,
  onSessionChange,
  openPlanTab,
  clearRunWatchdog,
  setRecoveryFailure,
}: RoomVerifiedHandlersOptions) {
  const handleVerifiedApprove = useCallback(
    async (mode: PlanApprovalMode = "approve_only") => {
      if (!sessionId || (!showPlanApproval && !verifiedEditGoal.trim())) return;
      setVerifiedLoopBusy(true);
      setVerifiedLoopError(null);
      try {
        const res = showPlanApproval
          ? await approvePlan(sessionId)
          : await approveVerifiedLoop(sessionId, {
              goal: verifiedEditGoal.trim(),
              completion_promise: verifiedEditPromise.trim() || "DONE",
              criteria: verifiedEditCriteria.trim() || verifiedEditGoal.trim(),
            });
        await refreshSessionMeta();
        if (showPlanApproval && mode === "execute") {
          await planExecute.dryRun();
        }
        const prompt =
          "continue_prompt" in res
            ? (res.continue_prompt as string | undefined)?.trim()
            : undefined;
        if (prompt && !showPlanApproval) {
          void executeSend(
            prompt,
            [],
            roomPermissions(selected),
          );
        }
      } catch (e) {
        setVerifiedLoopError(String(e));
      } finally {
        setVerifiedLoopBusy(false);
      }
    },
    [
      sessionId,
      verifiedEditGoal,
      verifiedEditCriteria,
      verifiedEditPromise,
      refreshSessionMeta,
      executeSend,
      selected,
      showPlanApproval,
      planExecute,
      setVerifiedLoopBusy,
      setVerifiedLoopError,
    ],
  );

  const handleVerifiedReject = useCallback(
    async (payload?: PlanRejectPayload) => {
      if (!sessionId) return;
      setVerifiedLoopBusy(true);
      setVerifiedLoopError(null);
      try {
        if (showPlanApproval) {
          await rejectPlan(sessionId, {
            note: payload?.note ?? "Human requested plan revise",
            target_phase: payload?.target_phase ?? "CLARIFY",
          });
        } else {
          await rejectVerifiedLoop(sessionId);
        }
        await refreshSessionMeta();
      } catch (e) {
        setVerifiedLoopError(String(e));
      } finally {
        setVerifiedLoopBusy(false);
      }
    },
    [sessionId, refreshSessionMeta, showPlanApproval, setVerifiedLoopBusy, setVerifiedLoopError],
  );

  const executeSynthesizeOnly = useCallback(
    async (permissions: AgentPermissions) => {
      if (!sessionId || synthesizing) return;
      const requestId = crypto.randomUUID();
      updateSessionRun(sessionId, {
        synthesizing: true,
        runBusy: true,
        running: true,
      });
      setRecoveryFailure(null);
      try {
        await runSynthesizeOnly(
          sessionId,
          (ev) => {
            if (String(ev.type) === "error") {
              setRecoveryFailure({
                source: "run",
                message: String(ev.message ?? "plan synthesis failed"),
              });
            }
          },
          { requestId, permissions },
        );
        openPlanTab();
        await onSessionChange(sessionId);
      } catch (e) {
        setRecoveryFailure({ source: "transport", message: String(e) });
      } finally {
        clearRunWatchdog();
        updateSessionRun(sessionId, {
          synthesizing: false,
          runBusy: false,
          running: false,
        });
      }
    },
    [
      sessionId,
      synthesizing,
      onSessionChange,
      openPlanTab,
      clearRunWatchdog,
      setRecoveryFailure,
    ],
  );

  const handleSynthesizeNow = useCallback(() => {
    if (
      running ||
      runBusy ||
      synthesizing ||
      !sessionId ||
      messages.length === 0
    ) {
      return;
    }
    void executeSynthesizeOnly(roomPermissions(selected));
  }, [
    running,
    runBusy,
    synthesizing,
    sessionId,
    messages.length,
    executeSynthesizeOnly,
    selected,
  ]);

  return {
    handleVerifiedApprove,
    handleVerifiedReject,
    handleSynthesizeNow,
    executeSynthesizeOnly,
  };
}
