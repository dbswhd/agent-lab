import { useEffect, useMemo, useState } from "react";
import {
  buildHumanDecisionLanes,
  humanDecisionBlockedLanes,
  shouldShowHumanDecisionBanner,
} from "../utils/humanDecisionView";
import { useSessionRuntime } from "./useSessionRuntime";

const DISCUSS_PAUSED_POLL_MS = 4000;

export function useHumanDecisionRuntime(
  sessionId: string | null,
  reloadKey: number,
  discussPaused: boolean,
) {
  // useSessionRuntime only refetches when reloadKey/run/sessionId change —
  // there's no periodic timer. If a *different* tab/session resolves the
  // Human Inbox item, this tab's discussPaused never flips back to false
  // (only the tab that performed the resolve does that) and its runtime
  // snapshot is never refetched, so the "Discuss blocked" banner would
  // otherwise never learn the gate reopened. Poll while paused and stop
  // as soon as a fresh snapshot confirms the gate is open again.
  const [pollTick, setPollTick] = useState(0);
  const { runtime } = useSessionRuntime(sessionId, {
    reloadKey: reloadKey + pollTick,
    enabled: true,
  });
  const discussGateOpen = runtime?.gates?.discuss?.open === true;

  useEffect(() => {
    if (!discussPaused || discussGateOpen) return;
    const timer = window.setInterval(() => {
      setPollTick((t) => t + 1);
    }, DISCUSS_PAUSED_POLL_MS);
    return () => window.clearInterval(timer);
  }, [discussPaused, discussGateOpen]);

  const lanes = useMemo(
    () => buildHumanDecisionLanes(runtime, discussPaused),
    [runtime, discussPaused],
  );
  const blocked = useMemo(() => humanDecisionBlockedLanes(lanes), [lanes]);
  const visible =
    shouldShowHumanDecisionBanner(runtime, discussPaused) && blocked.length > 0;

  return { runtime, lanes, blocked, visible };
}
