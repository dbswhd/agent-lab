import { useCallback, useEffect, useRef, useState } from "react";
import {
  getRunningSessionIds,
  updateSessionRun,
} from "../run/runSessionRegistry";

const LONG_RUN_HINT_MS = Number(
  import.meta.env.VITE_ROOM_LONG_RUN_HINT_MS || "180000",
);

const STOP_WATCHDOG_MS = 8_000;

/** Phase 1c (F6): run lock stuck + long-run hint timers — extracted from RoomChat. */
export function useRoomRunWatchdog(sessionId: string | null) {
  const runWatchdogRef = useRef<number | null>(null);
  const longRunHintRef = useRef<number | null>(null);
  const [longRunning, setLongRunning] = useState(false);
  const [runLockStuck, setRunLockStuck] = useState(false);
  const [releasingLock, setReleasingLock] = useState(false);

  const clearRunWatchdog = useCallback(() => {
    if (runWatchdogRef.current != null) {
      window.clearTimeout(runWatchdogRef.current);
      runWatchdogRef.current = null;
    }
  }, []);

  const clearLongRunHint = useCallback(() => {
    if (longRunHintRef.current != null) {
      window.clearTimeout(longRunHintRef.current);
      longRunHintRef.current = null;
    }
    setLongRunning(false);
  }, []);

  const scheduleLongRunHint = useCallback(() => {
    clearLongRunHint();
    if (LONG_RUN_HINT_MS <= 0) return;
    longRunHintRef.current = window.setTimeout(() => {
      setLongRunning(true);
      longRunHintRef.current = null;
    }, LONG_RUN_HINT_MS);
  }, [clearLongRunHint]);

  const armStopWatchdog = useCallback(() => {
    clearRunWatchdog();
    runWatchdogRef.current = window.setTimeout(() => {
      for (const id of getRunningSessionIds()) {
        updateSessionRun(id, { runBusy: false, running: false });
      }
      runWatchdogRef.current = null;
    }, STOP_WATCHDOG_MS);
  }, [clearRunWatchdog]);

  useEffect(() => {
    clearRunWatchdog();
  }, [sessionId, clearRunWatchdog]);

  return {
    longRunning,
    runLockStuck,
    setRunLockStuck,
    releasingLock,
    setReleasingLock,
    clearRunWatchdog,
    clearLongRunHint,
    scheduleLongRunHint,
    armStopWatchdog,
  };
}
