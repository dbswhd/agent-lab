import { useCallback, useSyncExternalStore } from "react";
import {
  getNotificationsSnapshot,
  markNotificationRead,
  subscribeNotifications,
  type AppNotification,
} from "../utils/notificationStore";
import {
  notificationActionForKind,
  notificationActionLabel,
} from "../utils/notificationActions";
import type { TranscriptActivityMarker } from "../utils/transcript";

type Props = {
  readonly marker: TranscriptActivityMarker;
  readonly locale: string;
  readonly onOpen?: (note: AppNotification) => void;
};

function tierClass(tier: TranscriptActivityMarker["tier"]): string {
  return `activity-divider--${tier.toLowerCase()}`;
}

function useNotificationById(id: string): AppNotification | undefined {
  const subscribe = useCallback(
    (onStoreChange: () => void) => subscribeNotifications(onStoreChange),
    [],
  );
  const getSnapshot = useCallback(() => {
    return getNotificationsSnapshot().find((n) => n.id === id);
  }, [id]);
  return useSyncExternalStore(subscribe, getSnapshot, () => undefined);
}

export function TranscriptActivityDivider({ marker, locale, onOpen }: Props) {
  const ko = locale === "ko";
  const live = useNotificationById(marker.id);
  const read = live?.read ?? marker.read;
  const action = notificationActionForKind(marker.kind);

  return (
    <div
      className={[
        "activity-divider",
        tierClass(marker.tier),
        read ? "is-read" : "",
      ]
        .filter(Boolean)
        .join(" ")}
      role="status"
      aria-label={marker.title}
    >
      <div className="activity-divider__content">
        <span className="activity-divider__title">{marker.title}</span>
        {marker.body ? (
          <span className="activity-divider__body">{marker.body}</span>
        ) : null}
        {action && onOpen ? (
          <button
            type="button"
            className="activity-divider__action"
            onClick={() => {
              markNotificationRead(marker.id);
              onOpen({
                id: marker.id,
                tier: marker.tier,
                title: marker.title,
                body: marker.body,
                kind: marker.kind,
                createdAt: marker.createdAt,
                read: true,
                sessionId: live?.sessionId,
                entityId: live?.entityId,
              });
            }}
          >
            {notificationActionLabel(action, ko)}
          </button>
        ) : null}
      </div>
    </div>
  );
}
