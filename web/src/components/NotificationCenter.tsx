import { useCallback, useSyncExternalStore } from "react";
import {
  getNotificationsSnapshot,
  markAllNotificationsRead,
  subscribeNotifications,
  unreadNotificationCount,
  type AppNotification,
} from "../utils/notificationStore";

function useNotificationStore() {
  const subscribe = useCallback(
    (onStoreChange: () => void) => subscribeNotifications(onStoreChange),
    [],
  );
  const items = useSyncExternalStore(
    subscribe,
    getNotificationsSnapshot,
    () => [],
  );
  const unread = useSyncExternalStore(
    subscribe,
    unreadNotificationCount,
    () => 0,
  );
  return { items, unread, markAllRead: markAllNotificationsRead };
}

function tierClass(tier: AppNotification["tier"]): string {
  return `notification-center__item--${tier.toLowerCase()}`;
}

type Props = {
  onOpen?: (notification: AppNotification) => void;
};

export function NotificationCenter({ onOpen }: Props = {}) {
  const { items, unread, markAllRead } = useNotificationStore();

  if (items.length === 0) {
    return (
      <p className="inspector-pane__empty notification-center__empty">
        아직 알림이 없습니다. 턴 완료·합의·execute 상태가 여기에 쌓입니다.
      </p>
    );
  }

  return (
    <div className="notification-center">
      <div className="notification-center__head">
        <strong>Activity</strong>
        {unread > 0 ? (
          <button
            type="button"
            className="mac-btn-secondary mac-btn-secondary--compact"
            onClick={markAllRead}
          >
            모두 읽음 ({unread})
          </button>
        ) : null}
      </div>
      <ul className="notification-center__list">
        {items.map((n) => (
          <li
            key={n.id}
            className={[
              "notification-center__item",
              tierClass(n.tier),
              n.read ? "is-read" : "",
            ]
              .filter(Boolean)
              .join(" ")}
          >
            <span className="notification-center__title">{n.title}</span>
            {n.body ? (
              <span className="notification-center__body">{n.body}</span>
            ) : null}
            <time className="notification-center__time">
              {new Date(n.createdAt).toLocaleTimeString("ko-KR", {
                hour: "2-digit",
                minute: "2-digit",
              })}
            </time>
            {onOpen ? (
              <button
                type="button"
                className="notification-center__open"
                onClick={() => onOpen(n)}
              >
                바로가기
              </button>
            ) : null}
          </li>
        ))}
      </ul>
    </div>
  );
}
