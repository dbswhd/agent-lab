import { useCallback, useSyncExternalStore } from "react";
import {
  getRunningSessionIds,
  subscribeAllSessionRuns,
} from "../run/runSessionRegistry";

let cachedKey = "";
let cachedIds: string[] = [];

function snapshotRunningIds(): string[] {
  const ids = getRunningSessionIds();
  const key = ids.join("\0");
  if (key !== cachedKey) {
    cachedKey = key;
    cachedIds = ids;
  }
  return cachedIds;
}

export function useRunningSessionIds(): string[] {
  const subscribe = useCallback(
    (onStoreChange: () => void) => subscribeAllSessionRuns(onStoreChange),
    [],
  );
  return useSyncExternalStore(subscribe, snapshotRunningIds, () => []);
}
