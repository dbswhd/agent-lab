import type { NotificationAction } from "../utils/notificationActions";

export type MacNotificationPayload = {
  title: string;
  body?: string;
  action?: NotificationAction;
  actionLabel?: string;
};

export type MacNotificationContextValue = {
  push: (payload: MacNotificationPayload) => void;
};
