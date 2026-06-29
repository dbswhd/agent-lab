import type { AppNotification } from "./notificationStore";
import { getNotificationsSnapshot } from "./notificationStore";
import type { LiveMsg } from "../run/runSessionRegistry";
import { updateSessionRun } from "../run/runSessionRegistry";
import type { TranscriptActivityMarker } from "./transcript";

export function isTranscriptActivityMessage(message: LiveMsg): boolean {
  return Boolean(message.activityMarker);
}

export function activityMarkerFromNotification(
  note: AppNotification,
): TranscriptActivityMarker {
  return {
    id: note.id,
    tier: note.tier,
    title: note.title,
    body: note.body,
    kind: note.kind,
    createdAt: note.createdAt,
    read: note.read,
  };
}

export function activityMessageFromNotification(
  note: AppNotification,
): LiveMsg {
  return {
    id: `activity-${note.id}`,
    role: "system",
    label: "",
    body: note.title,
    activityMarker: activityMarkerFromNotification(note),
  };
}

export function appendTranscriptActivity(
  sessionId: string,
  note: AppNotification,
): void {
  if (!sessionId) return;
  const marker = activityMessageFromNotification(note);
  updateSessionRun(sessionId, (snap) => {
    if (snap.messages.some((m) => m.id === marker.id)) return {};
    return {
      messages: [...snap.messages, marker],
      turnMessages: [...snap.turnMessages, marker],
    };
  });
}

export function mergeActivityMarkersFromLocal(
  base: LiveMsg[],
  local: LiveMsg[],
): LiveMsg[] {
  const markers = local.filter(isTranscriptActivityMessage);
  if (!markers.length) return base;
  const seen = new Set(base.map((m) => m.id));
  const additions = markers.filter((m) => !seen.has(m.id));
  if (!additions.length) return base;
  return [
    ...base,
    ...additions.sort(
      (a, b) =>
        (a.activityMarker?.createdAt ?? 0) - (b.activityMarker?.createdAt ?? 0),
    ),
  ];
}

export function syncSessionActivityMarkers(sessionId: string): void {
  for (const note of getNotificationsSnapshot()) {
    if (note.sessionId === sessionId) {
      appendTranscriptActivity(sessionId, note);
    }
  }
}
