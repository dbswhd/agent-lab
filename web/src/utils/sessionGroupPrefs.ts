import type { SessionSummary } from "../api/client";

const STORAGE_KEY = "agent-lab-session-groups";

export const SESSION_GROUP_UNGROUPED_LABEL = "그룹 없음";

type Store = {
  groups: string[];
  assignments: Record<string, string>;
  pinned: string[];
};

function emptyStore(): Store {
  return { groups: [], assignments: {}, pinned: [] };
}

function readStore(): Store {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return emptyStore();
    const parsed = JSON.parse(raw) as unknown;
    if (!parsed || typeof parsed !== "object") return emptyStore();
    const record = parsed as Record<string, unknown>;
    const groups = Array.isArray(record.groups)
      ? record.groups.filter(
          (value): value is string => typeof value === "string",
        )
      : [];
    const assignments: Record<string, string> = {};
    if (record.assignments && typeof record.assignments === "object") {
      for (const [sessionId, group] of Object.entries(
        record.assignments as Record<string, unknown>,
      )) {
        if (typeof group === "string" && group.trim()) {
          assignments[sessionId] = group.trim();
        }
      }
    }
    const pinned = Array.isArray(record.pinned)
      ? record.pinned.filter(
          (value): value is string => typeof value === "string",
        )
      : [];
    return { groups, assignments, pinned };
  } catch {
    return emptyStore();
  }
}

function writeStore(store: Store): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(store));
}

export function listSessionGroups(): string[] {
  return [...readStore().groups];
}

export function getSessionGroup(sessionId: string): string | null {
  return readStore().assignments[sessionId] ?? null;
}

export function isSessionPinned(sessionId: string): boolean {
  return readStore().pinned.includes(sessionId);
}

export function createSessionGroup(name: string): string | null {
  const trimmed = name.trim();
  if (!trimmed) return null;
  const store = readStore();
  if (
    store.groups.some(
      (group) => group.toLocaleLowerCase() === trimmed.toLocaleLowerCase(),
    )
  ) {
    return trimmed;
  }
  store.groups.push(trimmed);
  writeStore(store);
  return trimmed;
}

export function moveSessionToGroup(
  sessionId: string,
  group: string | null,
): void {
  const store = readStore();
  if (!group) {
    delete store.assignments[sessionId];
  } else {
    if (!store.groups.includes(group)) {
      store.groups.push(group);
    }
    store.assignments[sessionId] = group;
  }
  writeStore(store);
}

export function toggleSessionPinned(sessionId: string): boolean {
  const store = readStore();
  const index = store.pinned.indexOf(sessionId);
  if (index >= 0) {
    store.pinned.splice(index, 1);
    writeStore(store);
    return false;
  }
  store.pinned.push(sessionId);
  writeStore(store);
  return true;
}

export type SessionListGroup = {
  key: string;
  label: string;
  sessions: SessionSummary[];
};

function sessionSortRank(session: SessionSummary, pinned: string[]): number {
  const pinIndex = pinned.indexOf(session.id);
  if (pinIndex >= 0) return pinIndex;
  return pinned.length + 1;
}

function compareSessions(
  a: SessionSummary,
  b: SessionSummary,
  pinned: string[],
): number {
  const pinA = sessionSortRank(a, pinned);
  const pinB = sessionSortRank(b, pinned);
  if (pinA !== pinB) return pinA - pinB;
  const timeA = Date.parse(a.created_at ?? "") || 0;
  const timeB = Date.parse(b.created_at ?? "") || 0;
  return timeB - timeA;
}

export function groupSessionsForList(
  sessions: SessionSummary[],
): SessionListGroup[] {
  const { groups, assignments, pinned } = readStore();
  const buckets = new Map<string, SessionSummary[]>();

  for (const session of sessions) {
    const group = assignments[session.id] ?? SESSION_GROUP_UNGROUPED_LABEL;
    const bucket = buckets.get(group) ?? [];
    bucket.push(session);
    buckets.set(group, bucket);
  }

  const orderedLabels = [
    ...groups.filter((group) => buckets.has(group)),
    ...(buckets.has(SESSION_GROUP_UNGROUPED_LABEL)
      ? [SESSION_GROUP_UNGROUPED_LABEL]
      : []),
  ];

  return orderedLabels.map((label) => ({
    key: label,
    label,
    sessions: [...(buckets.get(label) ?? [])].sort((a, b) =>
      compareSessions(a, b, pinned),
    ),
  }));
}

export function groupLabelToAssignment(label: string): string | null {
  return label === SESSION_GROUP_UNGROUPED_LABEL ? null : label;
}

/** Include empty named groups as drop targets while dragging. */
export function groupSessionsForDrag(
  sessions: SessionSummary[],
): SessionListGroup[] {
  const grouped = groupSessionsForList(sessions);
  const existing = new Set(grouped.map((group) => group.key));
  const extras = listSessionGroups()
    .filter((name) => !existing.has(name))
    .map((name) => ({
      key: name,
      label: name,
      sessions: [] as SessionSummary[],
    }));
  if (!extras.length) return grouped;

  const ungroupedIndex = grouped.findIndex(
    (group) => group.key === SESSION_GROUP_UNGROUPED_LABEL,
  );
  if (ungroupedIndex >= 0) {
    return [
      ...grouped.slice(0, ungroupedIndex),
      ...extras,
      ...grouped.slice(ungroupedIndex),
    ];
  }
  return [...grouped, ...extras];
}
