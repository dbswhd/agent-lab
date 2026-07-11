import { useMemo } from "react";
import {
  buildHumanDecisionLanes,
  humanDecisionBlockedLanes,
  shouldShowHumanDecisionBanner,
} from "../utils/humanDecisionView";
import { useSessionRuntime } from "./useSessionRuntime";

export function useHumanDecisionRuntime(
  sessionId: string | null,
  reloadKey: number,
  discussPaused: boolean,
) {
  const { runtime } = useSessionRuntime(sessionId, {
    reloadKey,
    enabled: true,
  });

  const lanes = useMemo(
    () => buildHumanDecisionLanes(runtime, discussPaused),
    [runtime, discussPaused],
  );
  const blocked = useMemo(() => humanDecisionBlockedLanes(lanes), [lanes]);
  const visible =
    shouldShowHumanDecisionBanner(runtime, discussPaused) && blocked.length > 0;

  return { runtime, lanes, blocked, visible };
}
