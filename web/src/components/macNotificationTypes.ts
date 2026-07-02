import type { NotificationAction } from "../utils/notificationActions";

export type MacNotificationPayload = {
  title: string;
  body?: string;
  action?: NotificationAction;
  actionLabel?: string;
  variant?: "default" | "alert";
};

export type MacNotificationContextValue = {
  push: (payload: MacNotificationPayload) => void;
};
