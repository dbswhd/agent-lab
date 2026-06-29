export type NotificationAction =
  | { type: "work"; focus?: "execute" | "plan" }
  | { type: "composer"; focus?: "inbox" | "activity" | "execute" | "plan" }
  | { type: "inspector"; tab?: "overview" }
  | { type: "settings" };

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
    if (
      detail?.type === "work" ||
      detail?.type === "composer" ||
      detail?.type === "inspector" ||
      detail?.type === "settings"
    ) {
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
    return { type: "composer", focus: "execute" };
  }
  if (
    kind === "dry_run" ||
    kind === "plan_sync" ||
    kind === "consensus_complete"
  ) {
    return { type: "composer", focus: "plan" };
  }
  if (
    kind === "human_inbox" ||
    kind === "human_inbox_question" ||
    kind === "human_inbox_build"
  ) {
    return kind === "human_inbox_build"
      ? { type: "composer", focus: "plan" }
      : { type: "composer", focus: "inbox" };
  }
  if (kind === "verified_loop_pending") {
    return { type: "composer", focus: "plan" };
  }
  if (kind === "plan_workflow_pending") {
    return { type: "composer", focus: "plan" };
  }
  if (kind === "consensus_incomplete" || kind === "objection_open") {
    return { type: "inspector", tab: "overview" };
  }
  if (kind.startsWith("hook_")) {
    return { type: "settings" };
  }
  return null;
}

export function notificationActionLabel(
  action: NotificationAction,
  ko = true,
): string {
  if (action.type === "composer") {
    if (action.focus === "inbox") return ko ? "Composer로" : "Composer";
    if (action.focus === "execute") return ko ? "Execute" : "Execute";
    return ko ? "Plan" : "Plan";
  }
  if (action.type === "work") {
    return ko ? "Execute" : "Execute";
  }
  if (action.type === "inspector") return ko ? "Overview" : "Overview";
  return ko ? "Settings" : "Settings";
}

/** @deprecated Use notificationActionLabel */
export function defaultActionLabel(action: NotificationAction): string {
  return notificationActionLabel(action);
}

export function isNotificationActionable(action: NotificationAction): boolean {
  return action.type !== "settings";
}
