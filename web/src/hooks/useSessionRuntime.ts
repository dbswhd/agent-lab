import { useEffect, useState } from "react";
import { fetchSessionRuntime, type RuntimeSnapshot } from "../api/client";

export type UseSessionRuntimeOptions = {
  /** Bump after inbox/gate mutations that affect runtime.gates. */
  reloadKey?: number;
  /** Refetch when run.json changes (e.g. session.run). */
  run?: unknown;
  /** When false, skip fetch and clear cached runtime. */
  enabled?: boolean;
};

export type SessionRuntimeState = {
  runtime: RuntimeSnapshot | null;
  loading: boolean;
};

/** Shared `/runtime` fetch — one invalidation contract for Room UI surfaces. */
export function useSessionRuntime(
  sessionId: string | null,
  options: UseSessionRuntimeOptions = {},
): SessionRuntimeState {
  const { reloadKey = 0, run, enabled = true } = options;
  const [runtime, setRuntime] = useState<RuntimeSnapshot | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!sessionId || !enabled) {
      setRuntime(null);
      setLoading(false);
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
  }, [enabled, reloadKey, run, sessionId]);

  return { runtime, loading };
}
