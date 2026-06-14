import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import {
  defaultActionLabel,
  dispatchNotificationAction,
  type NotificationAction,
} from "../utils/notificationActions";

export type MacNotificationPayload = {
  title: string;
  body?: string;
  action?: NotificationAction;
  actionLabel?: string;
};

type MacNotificationItem = MacNotificationPayload & {
  id: string;
  createdAt: number;
};

type MacNotificationContextValue = {
  push: (payload: MacNotificationPayload) => void;
};

const MacNotificationContext =
  createContext<MacNotificationContextValue | null>(null);

const AUTO_DISMISS_MS = 7_000;

function formatTime(ts: number): string {
  return new Date(ts).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });
}

function NotifyCard({
  item,
  onDismiss,
}: {
  item: MacNotificationItem;
  onDismiss: (id: string) => void;
}) {
  useEffect(() => {
    const timer = window.setTimeout(() => onDismiss(item.id), AUTO_DISMISS_MS);
    return () => window.clearTimeout(timer);
  }, [item.id, onDismiss]);

  function handleOpen() {
    if (item.action) {
      dispatchNotificationAction(item.action);
    }
    onDismiss(item.id);
  }

  const actionLabel =
    item.actionLabel ?? (item.action ? defaultActionLabel(item.action) : null);

  return (
    <div
      className={[
        "notify-card",
        item.action ? "notify-card--actionable" : undefined,
      ]
        .filter(Boolean)
        .join(" ")}
      role="status"
      aria-live="polite"
    >
      <button
        type="button"
        className="notify-card__main"
        disabled={!item.action}
        onClick={item.action ? handleOpen : undefined}
      >
        <span className="notify-card__icon" aria-hidden="true">
          <svg width="15" height="15" viewBox="0 0 20 20" fill="none">
            <rect
              width="20"
              height="20"
              rx="5"
              fill="currentColor"
              opacity=".15"
            />
            <text
              x="10"
              y="14"
              textAnchor="middle"
              fontSize="11"
              fontWeight="700"
              fill="currentColor"
            >
              A
            </text>
          </svg>
        </span>
        <div className="notify-card__body">
          <div className="notify-card__title">{item.title}</div>
          {item.body ? (
            <div className="notify-card__desc">{item.body}</div>
          ) : null}
          {item.action && actionLabel ? (
            <span className="notify-card__action-hint">{actionLabel}</span>
          ) : null}
        </div>
        <time
          className="notify-card__time"
          dateTime={new Date(item.createdAt).toISOString()}
        >
          {formatTime(item.createdAt)}
        </time>
      </button>
      {item.action && actionLabel ? (
        <button type="button" className="notify-card__go" onClick={handleOpen}>
          {actionLabel}
        </button>
      ) : null}
      <button
        type="button"
        className="notify-card__close"
        aria-label="알림 닫기"
        onClick={() => onDismiss(item.id)}
      >
        ×
      </button>
    </div>
  );
}

/** MacNotificationProvider — wrap the app root.
 *
 *  Uses .notify-stack / .notify-card-* classes (overlays.css).
 *  Drop-in for old MacNotificationProvider (macos26 classes).
 *
 *  @example
 *    <MacNotificationProvider>
 *      <App />
 *    </MacNotificationProvider>
 *
 *  In any child:
 *    const { push } = useMacNotifications();
 *    push({ title: "Run complete", body: "Oracle verified" });
 */
export function MacNotificationProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<MacNotificationItem[]>([]);
  const seqRef = useRef(0);

  const dismiss = useCallback((id: string) => {
    setItems((prev) => prev.filter((item) => item.id !== id));
  }, []);

  const push = useCallback((payload: MacNotificationPayload) => {
    const id = `mac-notify-${Date.now()}-${seqRef.current++}`;
    setItems((prev) =>
      [...prev, { ...payload, id, createdAt: Date.now() }].slice(-4),
    );
  }, []);

  const value = useMemo(() => ({ push }), [push]);

  return (
    <MacNotificationContext.Provider value={value}>
      {children}
      <div
        className="notify-stack"
        aria-live="polite"
        aria-relevant="additions"
        aria-label="알림"
      >
        {items.map((item) => (
          <NotifyCard key={item.id} item={item} onDismiss={dismiss} />
        ))}
      </div>
    </MacNotificationContext.Provider>
  );
}

export function useMacNotifications(): MacNotificationContextValue {
  const ctx = useContext(MacNotificationContext);
  if (!ctx) {
    throw new Error(
      "useMacNotifications must be used inside <MacNotificationProvider>",
    );
  }
  return ctx;
}
