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
import { AppBrandIcon } from "./AppBrandIcon";

export type MacNotificationPayload = {
  title: string;
  body?: string;
};

type MacNotificationItem = MacNotificationPayload & {
  id: string;
  createdAt: number;
};

type MacNotificationContextValue = {
  push: (payload: MacNotificationPayload) => void;
};

const MacNotificationContext = createContext<MacNotificationContextValue | null>(
  null,
);

const AUTO_DISMISS_MS = 7000;

function formatNotifyTime(ts: number): string {
  return new Date(ts).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });
}

function MacNotificationCard({
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

  return (
    <div className="mac-notification" role="status" aria-live="polite">
      <AppBrandIcon className="mac-notification-icon" />
      <div className="mac-notification-body">
        <div className="mac-notification-title">{item.title}</div>
        {item.body ? (
          <div className="mac-notification-desc">{item.body}</div>
        ) : null}
      </div>
      <time className="mac-notification-time" dateTime={new Date(item.createdAt).toISOString()}>
        {formatNotifyTime(item.createdAt)}
      </time>
      <button
        type="button"
        className="mac-notification-close"
        aria-label="알림 닫기"
        onClick={() => onDismiss(item.id)}
      >
        ×
      </button>
    </div>
  );
}

export function MacNotificationProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<MacNotificationItem[]>([]);
  const seqRef = useRef(0);

  const dismiss = useCallback((id: string) => {
    setItems((prev) => prev.filter((item) => item.id !== id));
  }, []);

  const push = useCallback((payload: MacNotificationPayload) => {
    const id = `mac-notify-${Date.now()}-${seqRef.current++}`;
    setItems((prev) => {
      const next = [...prev, { ...payload, id, createdAt: Date.now() }];
      return next.slice(-4);
    });
  }, []);

  useEffect(() => {
    if (!import.meta.env.DEV) return;
    (
      window as Window & {
        __agentLabPushNotify?: (payload: MacNotificationPayload) => void;
      }
    ).__agentLabPushNotify = push;
    return () => {
      delete (
        window as Window & {
          __agentLabPushNotify?: (payload: MacNotificationPayload) => void;
        }
      ).__agentLabPushNotify;
    };
  }, [push]);

  const value = useMemo(() => ({ push }), [push]);

  return (
    <MacNotificationContext.Provider value={value}>
      {children}
      <div className="mac-notification-stack" aria-live="polite" aria-relevant="additions">
        {items.map((item) => (
          <MacNotificationCard key={item.id} item={item} onDismiss={dismiss} />
        ))}
      </div>
    </MacNotificationContext.Provider>
  );
}

export function useMacNotifications(): MacNotificationContextValue {
  const ctx = useContext(MacNotificationContext);
  if (!ctx) {
    throw new Error("useMacNotifications must be used within MacNotificationProvider");
  }
  return ctx;
}
