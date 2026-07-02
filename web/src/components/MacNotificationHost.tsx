import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import {
  defaultActionLabel,
  dispatchNotificationAction,
} from "../utils/notificationActions";
import { ComposerNoticeCard } from "./ComposerNoticeCard";
import { MacNotificationContext } from "./macNotificationContext";
import type { MacNotificationPayload } from "./macNotificationTypes";

export type { MacNotificationPayload } from "./macNotificationTypes";

type MacNotificationItem = MacNotificationPayload & {
  id: string;
  createdAt: number;
};

const AUTO_DISMISS_MS = 7_000;

function NotifyCard({
  item,
  onDismiss,
}: {
  item: MacNotificationItem;
  onDismiss: (id: string) => void;
}) {
  useEffect(() => {
    if (item.variant === "alert") return;
    const timer = window.setTimeout(() => onDismiss(item.id), AUTO_DISMISS_MS);
    return () => window.clearTimeout(timer);
  }, [item.id, item.variant, onDismiss]);

  function handleOpen() {
    if (item.action) {
      dispatchNotificationAction(item.action);
    }
    onDismiss(item.id);
  }

  const actionLabel =
    item.actionLabel ?? (item.action ? defaultActionLabel(item.action) : null);

  return (
    <ComposerNoticeCard
      title={item.title}
      description={item.body ?? ""}
      variant={item.variant ?? "default"}
      primaryLabel={actionLabel ?? undefined}
      onPrimary={item.action ? handleOpen : undefined}
      onDismiss={() => onDismiss(item.id)}
      dismissLabel="닫기"
    />
  );
}

/** MacNotificationProvider — wrap the app root (overlays.css notify-stack). */
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
