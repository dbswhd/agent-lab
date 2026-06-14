import { createContext } from "react";
import type { MacNotificationContextValue } from "./macNotificationTypes";

export const MacNotificationContext =
  createContext<MacNotificationContextValue | null>(null);
