import { useCallback, useMemo, useState } from "react";
import { patchSessionAutonomy, type RuntimeSnapshot } from "../api/client";
import { useLocale } from "../i18n/useLocale";
import { useSessionRuntime } from "./useSessionRuntime";
import {
  autonomyFromSessionRun,
  buildAutonomySessionView,
  type AutonomyLevel,
  type AutonomySessionView,
} from "../utils/autonomyLadder";

export type UseAutonomySessionArgs = {
  sessionId: string | null;
  sessionRun?: Record<string, unknown> | null;
  reloadKey?: number;
};

/** N4: session autonomy ladder + trust budget — converged read path for UI. */
export function useAutonomySession({
  sessionId,
  sessionRun,
  reloadKey = 0,
}: UseAutonomySessionArgs): {
  view: AutonomySessionView | null;
  loading: boolean;
  changing: boolean;
  runtime: RuntimeSnapshot | null;
  refresh: () => void;
  setLevel: (level: AutonomyLevel) => Promise<void>;
} {
  const { locale } = useLocale();
  const [changing, setChanging] = useState(false);
  const [tick, setTick] = useState(0);

  const refresh = useCallback(() => setTick((n) => n + 1), []);

  const { runtime, loading } = useSessionRuntime(sessionId, {
    reloadKey: reloadKey + tick,
    run: sessionRun,
  });

  const view = useMemo(() => {
    const fromRuntime = buildAutonomySessionView(runtime?.autonomy, locale);
    if (fromRuntime) return fromRuntime;
    return buildAutonomySessionView(
      autonomyFromSessionRun(sessionRun ?? undefined),
      locale,
    );
  }, [locale, runtime?.autonomy, sessionRun]);

  const setLevel = useCallback(
    async (level: AutonomyLevel) => {
      if (!sessionId) return;
      setChanging(true);
      try {
        await patchSessionAutonomy(sessionId, level);
        refresh();
      } finally {
        setChanging(false);
      }
    },
    [sessionId, refresh],
  );

  return { view, loading, changing, runtime, refresh, setLevel };
}
