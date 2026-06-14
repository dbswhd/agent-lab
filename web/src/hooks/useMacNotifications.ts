import { useContext } from "react";
import { MacNotificationContext } from "../components/macNotificationContext";
import type { MacNotificationContextValue } from "../components/macNotificationTypes";

export function useMacNotifications(): MacNotificationContextValue {
  const ctx = useContext(MacNotificationContext);
  if (!ctx) {
    throw new Error(
      "useMacNotifications must be used inside <MacNotificationProvider>",
    );
  }
  return ctx;
}
