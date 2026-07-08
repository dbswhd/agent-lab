import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type Dispatch,
  type SetStateAction,
} from "react";
import { autoSyncSessionPlan } from "../api/client";
import type { ConsensusDryRunProposal } from "../components/ConsensusDryRunGateBar";
import {
  agreementPlanSyncFailedLabel,
  consensusDryRunNotifyBody,
  consensusDryRunNotifyTitle,
  latestPendingConsensusAgreement,
} from "../utils/consensusAgreement";
import { composerPlanStaleNotice } from "../utils/planMeta";
import { dispatchNotification } from "../utils/pushNotification";
import { notifyDesktop } from "../utils/desktopNotify";
import type { ComposerTurnProfile } from "../utils/turnProfile";
import type { usePlanExecute } from "./usePlanExecute";

type PlanExecuteSlice = Pick<
  ReturnType<typeof usePlanExecute>,
  "setSelectedKey" | "refreshActions" | "dryRun"
>;

export type RoomConsensusHandlersOptions = {
  sessionId: string | null;
  sessionRun: Record<string, unknown> | undefined;
  turnProfile: ComposerTurnProfile;
  running: boolean;
  runBusy: boolean;
  synthesizing: boolean;
  planExecute: PlanExecuteSlice;
  pushMacNotification: (payload: { title: string; body?: string }) => void;
  refreshSessionMeta: () => void;
  setInboxReloadKey: Dispatch<SetStateAction<number>>;
};

/** Consensus dry-run state, notifications, and plan auto-sync — extracted from RoomChat (F9). */
export function useRoomConsensusHandlers({
  sessionId,
  sessionRun,
  turnProfile,
  running,
  runBusy,
  synthesizing,
  planExecute,
  pushMacNotification,
  refreshSessionMeta,
  setInboxReloadKey,
}: RoomConsensusHandlersOptions) {
  const [consensusProposal, setConsensusProposal] =
    useState<ConsensusDryRunProposal | null>(null);
  const [consensusGateBusy, setConsensusGateBusy] = useState(false);
  const planAutoSyncRef = useRef<string | null>(null);

  useEffect(() => {
    setConsensusProposal(null);
  }, [sessionId]);

  const notifyConsensusSync = useCallback(
    (proposal: ConsensusDryRunProposal) => {
      const title = consensusDryRunNotifyTitle(proposal.excerpt);
      const body = consensusDryRunNotifyBody(
        proposal.summary,
        proposal.recommended?.what,
      );
      const freeConsensus = turnProfile === "loop";
      dispatchNotification(
        {
          tier: "P1",
          title,
          body,
          sessionId: sessionId ?? undefined,
          kind: proposal.recommended ? "consensus_complete" : "plan_sync",
          entityId: proposal.action_key ?? proposal.excerpt,
          toastAction: freeConsensus
            ? { type: "composer", focus: "plan" }
            : undefined,
        },
        pushMacNotification,
        notifyDesktop,
      );
    },
    [pushMacNotification, sessionId, turnProfile],
  );

  const notifyConsensusFailure = useCallback(
    (excerpt?: string, message?: string) => {
      const title = agreementPlanSyncFailedLabel(excerpt, message);
      dispatchNotification(
        {
          tier: "P0",
          title,
          sessionId: sessionId ?? undefined,
          kind: "plan_sync_fail",
          entityId: excerpt,
        },
        pushMacNotification,
        notifyDesktop,
      );
    },
    [pushMacNotification, sessionId],
  );

  const handleConsensusDryRun = useCallback(async () => {
    const key = consensusProposal?.action_key;
    if (!key) return;
    setConsensusGateBusy(true);
    try {
      planExecute.setSelectedKey(key);
      await planExecute.refreshActions();
      const ok = await planExecute.dryRun(key);
      if (ok) setConsensusProposal(null);
    } finally {
      setConsensusGateBusy(false);
    }
  }, [consensusProposal, planExecute]);

  const dismissConsensusProposal = useCallback(() => {
    setConsensusProposal(null);
  }, []);

  const composerPlanStale = composerPlanStaleNotice(sessionRun);
  const planAutoSyncKey = composerPlanStale
    ? `${sessionId ?? ""}:${composerPlanStale}`
    : null;

  useEffect(() => {
    if (!sessionId || !planAutoSyncKey || running || synthesizing || runBusy) {
      return;
    }
    if (planAutoSyncRef.current === planAutoSyncKey) return;
    planAutoSyncRef.current = planAutoSyncKey;
    void autoSyncSessionPlan(sessionId)
      .then((detail) => {
        const pending = latestPendingConsensusAgreement(detail.run);
        if (pending?.excerpt) {
          notifyConsensusFailure(
            pending.excerpt,
            "plan.md 자동 정리에 실패했습니다",
          );
          planAutoSyncRef.current = null;
          return;
        }
        refreshSessionMeta();
        setInboxReloadKey((k) => k + 1);
      })
      .catch(() => {
        notifyConsensusFailure(undefined, "plan.md 자동 정리 요청 실패");
        planAutoSyncRef.current = null;
      });
  }, [
    notifyConsensusFailure,
    planAutoSyncKey,
    refreshSessionMeta,
    runBusy,
    running,
    sessionId,
    setInboxReloadKey,
    synthesizing,
  ]);

  return {
    consensusProposal,
    setConsensusProposal,
    consensusGateBusy,
    notifyConsensusSync,
    notifyConsensusFailure,
    handleConsensusDryRun,
    dismissConsensusProposal,
    composerPlanStale,
  };
}
