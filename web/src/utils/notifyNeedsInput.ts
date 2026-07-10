import type { NeedsInputStatus } from "./needsInputStatus";
import { notifyDesktop } from "./desktopNotify";
import { dispatchNotification, type ToastPayload } from "./pushNotification";

type MacPush = (input: ToastPayload) => void;

const _lastNotified = new Map<string, number>();
const DEDUP_MS = 30_000;

function focusForStatus(
  status: NeedsInputStatus,
): "inbox" | "plan" | "execute" {
  if (status.focus === "plan_approval") return "plan";
  if (status.focus === "execute_queue") return "execute";
  if (status.focus === "inbox") return "inbox";
  return "inbox";
}

/** OS/desktop alert when Needs input is active and the document is hidden. */
export function notifyNeedsInputIfBackground(opts: {
  sessionId: string;
  status: NeedsInputStatus;
  locale?: "ko" | "en";
  macPush?: MacPush;
  force?: boolean;
}): boolean {
  const { sessionId, status, locale = "ko", macPush, force = false } = opts;
  if (!status.active || !sessionId) return false;
  if (
    !force &&
    typeof document !== "undefined" &&
    !document.hidden
  ) {
    return false;
  }

  const key = `${sessionId}:needs_input:${status.focus}`;
  const now = Date.now();
  const prev = _lastNotified.get(key) ?? 0;
  if (now - prev < DEDUP_MS) return false;
  _lastNotified.set(key, now);

  const ko = locale !== "en";
  const title = ko ? "Needs input" : "Needs input";
  const body = status.label || (ko ? "입력이 필요합니다" : "Waiting on you");
  const focus = focusForStatus(status);

  dispatchNotification(
    {
      tier: "P1",
      title,
      body,
      sessionId,
      kind: "needs_input",
      entityId: status.focus,
      forceToast: true,
      toastAction: { type: "composer", focus },
      toastActionLabel: ko ? "열기" : "Open",
    },
    macPush,
    notifyDesktop,
  );
  return true;
}

/** Lightweight notify from session-rail inbox poll (no full status object). */
export function notifyNeedsInputFromInboxPoll(opts: {
  sessionIds: string[];
  locale?: "ko" | "en";
}): void {
  if (typeof document !== "undefined" && !document.hidden) return;
  const ko = opts.locale !== "en";
  for (const sessionId of opts.sessionIds.slice(0, 5)) {
    const key = `${sessionId}:needs_input:inbox_poll`;
    const now = Date.now();
    const prev = _lastNotified.get(key) ?? 0;
    if (now - prev < DEDUP_MS) continue;
    _lastNotified.set(key, now);
    dispatchNotification(
      {
        tier: "P1",
        title: ko ? "Needs input" : "Needs input",
        body: ko ? "Inbox 대기 중" : "Inbox waiting",
        sessionId,
        kind: "needs_input",
        entityId: "inbox_poll",
        forceToast: true,
        toastAction: { type: "composer", focus: "inbox" },
      },
      undefined,
      notifyDesktop,
    );
  }
}
