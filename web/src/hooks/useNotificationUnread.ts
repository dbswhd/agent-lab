import { useCallback, useSyncExternalStore } from "react";
import {
  subscribeNotifications,
  unreadNotificationCount,
} from "../utils/notificationStore";

export function useNotificationUnread(): number {
  const subscribe = useCallback(
    (onStoreChange: () => void) => subscribeNotifications(onStoreChange),
    [],
  );
  return useSyncExternalStore(subscribe, unreadNotificationCount, () => 0);
}
