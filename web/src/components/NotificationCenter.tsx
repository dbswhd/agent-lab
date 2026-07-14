import { useCallback, useSyncExternalStore } from "react";
import {
  getNotificationsSnapshot,
  markAllNotificationsRead,
  subscribeNotifications,
  unreadNotificationCount,
  type AppNotification,
} from "../utils/notificationStore";
import { useMissionReadModel } from "../utils/missionReadModel";

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
  sessionId?: string | null;
  hideEmpty?: boolean;
};

export function NotificationCenter({
  onOpen,
  sessionId = null,
  hideEmpty = false,
}: Props = {}) {
  const { items, unread, markAllRead } = useNotificationStore();
  const { model } = useMissionReadModel(sessionId);
  const gateCount =
    model?.inbox_items?.filter(
      (item) => item.status === "pending" && item.actionable !== false,
    ).length ?? 0;

  if (items.length === 0 && gateCount === 0) {
    if (hideEmpty) return null;
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
      {gateCount > 0 ? (
        <p className="notification-center__body" role="status">
          {gateCount} human decision{gateCount === 1 ? "" : "s"} pending
        </p>
      ) : null}
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
