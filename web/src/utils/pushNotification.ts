import {
  pushAppNotification,
  type NotificationTier,
} from "./notificationStore";
import { appendTranscriptActivity } from "./transcriptActivity";
import {
  defaultActionLabel,
  type NotificationAction,
} from "./notificationActions";

export type ToastPayload = {
  title: string;
  body?: string;
  action?: NotificationAction;
  actionLabel?: string;
  variant?: "default" | "alert";
};

type PushInput = {
  tier: NotificationTier;
  title: string;
  body?: string;
  sessionId?: string;
  kind: string;
  entityId?: string;
  /** When set, show toast with shortcut navigation (also stored in inbox). */
  toastAction?: NotificationAction;
  toastActionLabel?: string;
  /** Force toast even for P2/P3 (default: P0/P1 only, or when toastAction set). */
  forceToast?: boolean;
};

type MacPush = (input: ToastPayload) => void;
type DesktopPush = (title: string, body?: string) => void;

const TOAST_KINDS = new Set([
  "execute_pending",
  "execute_blocked",
  "execute_queue",
  "dry_run",
  "plan_sync",
  "consensus_complete",
  "human_inbox_question",
  "human_inbox_build",
  "verified_loop_pending",
  "verified_loop_done",
  "verified_loop_failed",
  "hook_blocked",
  "hook_warn",
  "envelope_warn",
  "needs_input",
]);

export function shouldToastNotification(input: PushInput): boolean {
  if (input.kind === "plan_sync_fail") return false;
  if (input.forceToast || input.toastAction) return true;
  if (input.tier === "P0") return true;
  if (input.tier === "P1") return TOAST_KINDS.has(input.kind);
  return false;
}

export function dispatchNotification(
  input: PushInput,
  macPush?: MacPush,
  desktopPush?: DesktopPush,
): void {
  const note = pushAppNotification(input);
  if (!note) return;
  if (input.sessionId) {
    appendTranscriptActivity(input.sessionId, note);
  }

  if (!shouldToastNotification(input)) return;

  const action = input.toastAction;
  macPush?.({
    title: input.title,
    body: input.body,
    action,
    actionLabel:
      input.toastActionLabel ??
      (action ? defaultActionLabel(action) : undefined),
    variant: input.tier === "P0" ? "alert" : "default",
  });

  if (input.tier === "P0" || input.tier === "P1" || input.forceToast) {
    desktopPush?.(input.title, input.body);
  }
}
