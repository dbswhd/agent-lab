import { useCallback, useEffect, useMemo, useState } from "react";
import { checkSessionGoal, setSessionGoal } from "../api/client";
import {
  buildVerifiedLoopView,
  type VerifiedLoopView,
} from "../utils/verifiedLoopView";

export interface GoalLoopState {
  goalText: string;
  setGoalText: (text: string) => void;
  goalBusy: boolean;
  goalError: string | null;
  setGoalError: (err: string | null) => void;
  verifiedEditGoal: string;
  setVerifiedEditGoal: (v: string) => void;
  verifiedEditCriteria: string;
  setVerifiedEditCriteria: (v: string) => void;
  verifiedEditPromise: string;
  setVerifiedEditPromise: (v: string) => void;
  verifiedLoopBusy: boolean;
  setVerifiedLoopBusy: (v: boolean) => void;
  verifiedLoopError: string | null;
  setVerifiedLoopError: (v: string | null) => void;
  verifiedLoopView: VerifiedLoopView;
  handleGoalSave: () => Promise<void>;
  handleGoalCheck: () => Promise<void>;
}

export function useGoalLoop(
  sessionId: string | null,
  run: Record<string, unknown> | undefined,
  refreshSessionMeta: () => void | Promise<void>,
): GoalLoopState {
  const [goalText, setGoalText] = useState("");
  const [goalBusy, setGoalBusy] = useState(false);
  const [goalError, setGoalError] = useState<string | null>(null);
  const [verifiedEditGoal, setVerifiedEditGoal] = useState("");
  const [verifiedEditCriteria, setVerifiedEditCriteria] = useState("");
  const [verifiedEditPromise, setVerifiedEditPromise] = useState("DONE");
  const [verifiedLoopBusy, setVerifiedLoopBusy] = useState(false);
  const [verifiedLoopError, setVerifiedLoopError] = useState<string | null>(
    null,
  );

  const verifiedLoopView = useMemo(() => buildVerifiedLoopView(run), [run]);

  useEffect(() => {
    setVerifiedEditGoal(verifiedLoopView.proposedGoal);
    setVerifiedEditCriteria(verifiedLoopView.criteria);
    setVerifiedEditPromise(verifiedLoopView.completionPromise || "DONE");
    setVerifiedLoopError(null);
  }, [
    sessionId,
    verifiedLoopView.proposedGoal,
    verifiedLoopView.criteria,
    verifiedLoopView.completionPromise,
  ]);

  const handleGoalSave = useCallback(async () => {
    if (!sessionId || !goalText.trim()) return;
    setGoalBusy(true);
    setGoalError(null);
    try {
      await setSessionGoal(sessionId, { text: goalText.trim() });
      await refreshSessionMeta();
    } catch (e) {
      setGoalError(String(e));
    } finally {
      setGoalBusy(false);
    }
  }, [sessionId, goalText, refreshSessionMeta]);

  const handleGoalCheck = useCallback(async () => {
    if (!sessionId) return;
    setGoalBusy(true);
    setGoalError(null);
    try {
      const res = await checkSessionGoal(sessionId);
      if (res.reason) setGoalError(res.reason);
      await refreshSessionMeta();
    } catch (e) {
      setGoalError(String(e));
    } finally {
      setGoalBusy(false);
    }
  }, [sessionId, refreshSessionMeta]);

  return {
    goalText,
    setGoalText,
    goalBusy,
    goalError,
    setGoalError,
    verifiedEditGoal,
    setVerifiedEditGoal,
    verifiedEditCriteria,
    setVerifiedEditCriteria,
    verifiedEditPromise,
    setVerifiedEditPromise,
    verifiedLoopBusy,
    setVerifiedLoopBusy,
    verifiedLoopError,
    setVerifiedLoopError,
    verifiedLoopView,
    handleGoalSave,
    handleGoalCheck,
  };
}
