export type NotificationTier = "P0" | "P1" | "P2" | "P3";

export type AppNotification = {
  id: string;
  tier: NotificationTier;
  title: string;
  body?: string;
  sessionId?: string;
  kind: string;
  entityId?: string;
  createdAt: number;
  read: boolean;
};

const DEDUP_MS = 30_000;
const MAX_ITEMS = 100;

let items: AppNotification[] = [];
const listeners = new Set<() => void>();
const recentKeys = new Map<string, number>();

function notify() {
  listeners.forEach((fn) => fn());
}

export function subscribeNotifications(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function getNotificationsSnapshot(): AppNotification[] {
  return items;
}

export function unreadNotificationCount(): number {
  return items.filter((n) => !n.read).length;
}

export function markAllNotificationsRead(): void {
  items = items.map((n) => ({ ...n, read: true }));
  notify();
}

export function pushAppNotification(input: {
  tier: NotificationTier;
  title: string;
  body?: string;
  sessionId?: string;
  kind: string;
  entityId?: string;
}): AppNotification | null {
  const key = `${input.sessionId ?? ""}:${input.kind}:${input.entityId ?? ""}`;
  const now = Date.now();
  if (input.tier !== "P0") {
    const last = recentKeys.get(key);
    if (last != null && now - last < DEDUP_MS) return null;
  }
  recentKeys.set(key, now);

  const note: AppNotification = {
    id: `${now}-${Math.random().toString(36).slice(2, 8)}`,
    ...input,
    createdAt: now,
    read: false,
  };
  items = [note, ...items].slice(0, MAX_ITEMS);
  notify();
  return note;
}
