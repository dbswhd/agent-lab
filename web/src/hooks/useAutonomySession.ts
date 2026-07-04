import { useCallback, useEffect, useMemo, useState } from "react";
import {
  fetchSessionRuntime,
  patchSessionAutonomy,
  type RuntimeSnapshot,
} from "../api/client";
import { useLocale } from "../i18n/useLocale";
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
  const [runtime, setRuntime] = useState<RuntimeSnapshot | null>(null);
  const [loading, setLoading] = useState(false);
  const [changing, setChanging] = useState(false);
  const [tick, setTick] = useState(0);

  const refresh = useCallback(() => setTick((n) => n + 1), []);

  useEffect(() => {
    if (!sessionId) {
      setRuntime(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    void fetchSessionRuntime(sessionId)
      .then((payload) => {
        if (!cancelled) setRuntime(payload);
      })
      .catch(() => {
        if (!cancelled) setRuntime(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [sessionId, reloadKey, tick]);

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
        const res = await patchSessionAutonomy(sessionId, level);
        setRuntime((prev) =>
          prev
            ? { ...prev, autonomy: res.autonomy }
            : ({ autonomy: res.autonomy } as RuntimeSnapshot),
        );
      } finally {
        setChanging(false);
      }
    },
    [sessionId],
  );

  return { view, loading, changing, runtime, refresh, setLevel };
}
