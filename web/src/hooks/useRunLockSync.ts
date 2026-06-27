import { useEffect, useRef } from "react";
import { fetchRoomRunLock } from "../api/client";
import { syncSessionFromServerLock } from "../run/runSessionRegistry";

const POLL_ACTIVE_MS = 1500;
const POLL_IDLE_MS = 4000;

/** Poll server run-lock and mirror background runs into the session registry. */
export function useRunLockSync(enabled = true): void {
  const lockedRef = useRef(false);

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    let timer: number | null = null;

    async function tick() {
      try {
        const status = await fetchRoomRunLock();
        if (cancelled) return;
        lockedRef.current = Boolean(status.locked);
        syncSessionFromServerLock(status);
      } catch {
        /* best-effort — UI still has local SSE state */
      }
      if (!cancelled) {
        timer = window.setTimeout(
          tick,
          lockedRef.current ? POLL_ACTIVE_MS : POLL_IDLE_MS,
        );
      }
    }

    void tick();
    return () => {
      cancelled = true;
      if (timer != null) window.clearTimeout(timer);
    };
  }, [enabled]);
}
