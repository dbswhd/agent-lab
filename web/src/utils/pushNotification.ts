import { pushAppNotification, type NotificationTier } from "./notificationStore";

type PushInput = {
  tier: NotificationTier;
  title: string;
  body?: string;
  sessionId?: string;
  kind: string;
  entityId?: string;
};

type MacPush = (input: { title: string; body?: string }) => void;
type DesktopPush = (title: string, body?: string) => void;

export function dispatchNotification(
  input: PushInput,
  macPush?: MacPush,
  desktopPush?: DesktopPush,
): void {
  const note = pushAppNotification(input);
  if (!note) return;
  if (input.tier === "P0" || input.tier === "P1") {
    macPush?.({ title: input.title, body: input.body });
    desktopPush?.(input.title, input.body);
  }
}
