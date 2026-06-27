import { useEffect, useMemo, useState } from "react";
import { fetchSessionRuntime, type RuntimeSnapshot } from "../api/client";
import {
  buildHumanDecisionLanes,
  humanDecisionBlockedLanes,
  shouldShowHumanDecisionBanner,
} from "../utils/humanDecisionView";

export function useHumanDecisionRuntime(
  sessionId: string | null,
  reloadKey: number,
  discussPaused: boolean,
) {
  const [runtime, setRuntime] = useState<RuntimeSnapshot | null>(null);

  useEffect(() => {
    if (!sessionId) {
      setRuntime(null);
      return;
    }
    let cancelled = false;
    void fetchSessionRuntime(sessionId)
      .then((snap) => {
        if (!cancelled) setRuntime(snap);
      })
      .catch(() => {
        if (!cancelled) setRuntime(null);
      });
    return () => {
      cancelled = true;
    };
  }, [sessionId, reloadKey, discussPaused]);

  const lanes = useMemo(
    () => buildHumanDecisionLanes(runtime, discussPaused),
    [runtime, discussPaused],
  );
  const blocked = useMemo(() => humanDecisionBlockedLanes(lanes), [lanes]);
  const visible =
    shouldShowHumanDecisionBanner(runtime, discussPaused) && blocked.length > 0;

  return { runtime, lanes, blocked, visible };
}
