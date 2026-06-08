export type NotificationAction =
  | { type: "work"; focus?: "execute" | "plan" }
  | { type: "inbox" }
  | { type: "inspector"; tab?: "overview" | "tasks" | "inbox" };

export const NOTIFICATION_ACTION_EVENT = "agent-lab-notification-action";

export function dispatchNotificationAction(action: NotificationAction): void {
  window.dispatchEvent(
    new CustomEvent(NOTIFICATION_ACTION_EVENT, { detail: action }),
  );
}

export function subscribeNotificationActions(
  handler: (action: NotificationAction) => void,
): () => void {
  function onEvent(event: Event) {
    const detail = (event as CustomEvent<NotificationAction>).detail;
    if (detail?.type === "work" || detail?.type === "inbox" || detail?.type === "inspector") {
      handler(detail);
    }
  }
  window.addEventListener(NOTIFICATION_ACTION_EVENT, onEvent);
  return () => window.removeEventListener(NOTIFICATION_ACTION_EVENT, onEvent);
}

/** Map persisted inbox notification kinds → navigation target. */
export function notificationActionForKind(
  kind: string,
): NotificationAction | null {
  if (
    kind === "execute_pending" ||
    kind === "execute_blocked" ||
    kind === "execute_queue"
  ) {
    return { type: "work", focus: "execute" };
  }
  if (
    kind === "dry_run" ||
    kind === "plan_sync" ||
    kind === "consensus_complete"
  ) {
    return { type: "work", focus: "plan" };
  }
  if (
    kind === "human_inbox" ||
    kind === "human_inbox_question" ||
    kind === "human_inbox_build"
  ) {
    return kind === "human_inbox_build"
      ? { type: "work", focus: "plan" }
      : { type: "inbox" };
  }
  if (kind === "verified_loop_pending") {
    return { type: "inspector", tab: "tasks" };
  }
  return null;
}

export function defaultActionLabel(
  action: NotificationAction,
  locale: "ko" | "en" = "ko",
): string {
  if (action.type === "inbox") {
    return locale === "ko" ? "Inbox 열기" : "Open Inbox";
  }
  if (action.type === "inspector") {
    return locale === "ko" ? "Inspector · Tasks" : "Inspector · Tasks";
  }
  if (action.focus === "execute") {
    return locale === "ko" ? "Work · Execute" : "Work · Execute";
  }
  return locale === "ko" ? "Work · Plan" : "Work · Plan";
}
