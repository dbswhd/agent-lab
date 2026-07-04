import { useEffect, useMemo, useState } from "react";
import { fetchSessionRuntime, type RuntimeSnapshot } from "../api/client";
import { useLocale } from "../i18n/useLocale";
import {
  autonomyFromSessionRun,
  buildAutonomySessionView,
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
  runtime: RuntimeSnapshot | null;
  refresh: () => void;
} {
  const { locale } = useLocale();
  const [runtime, setRuntime] = useState<RuntimeSnapshot | null>(null);
  const [loading, setLoading] = useState(false);
  const [tick, setTick] = useState(0);

  const refresh = () => setTick((n) => n + 1);

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

  return { view, loading, runtime, refresh };
}
