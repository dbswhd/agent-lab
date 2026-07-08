import type { WorkspaceFileRoot } from "../api/client";

const STORAGE_KEY = "agent-lab-files-visible-roots";

type Store = Record<string, string[]>;

function readAll(): Store {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw) as unknown;
    if (!parsed || typeof parsed !== "object") return {};
    const out: Store = {};
    for (const [sessionId, value] of Object.entries(parsed)) {
      if (!Array.isArray(value)) continue;
      out[sessionId] = value.filter(
        (id): id is string => typeof id === "string",
      );
    }
    return out;
  } catch {
    return {};
  }
}

function writeAll(store: Store): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(store));
}

/** Empty = show every root returned by the API. */
export function getVisibleRootIds(sessionId: string): string[] {
  return readAll()[sessionId] ?? [];
}

export function setVisibleRootIds(sessionId: string, rootIds: string[]): void {
  const store = readAll();
  if (!rootIds.length) {
    delete store[sessionId];
  } else {
    store[sessionId] = [...rootIds];
  }
  writeAll(store);
}

export function resolveVisibleRoots(
  allRoots: WorkspaceFileRoot[],
  visibleIds: string[],
): WorkspaceFileRoot[] {
  if (!visibleIds.length) return allRoots;
  const byId = new Map(allRoots.map((root) => [root.root_id, root]));
  const visible = visibleIds
    .map((id) => byId.get(id))
    .filter((root): root is WorkspaceFileRoot => root != null);
  return visible.length > 0 ? visible : allRoots;
}

export function toggleVisibleRoot(
  visibleIds: string[],
  allRootIds: string[],
  rootId: string,
): string[] {
  const base = visibleIds.length ? visibleIds : [...allRootIds];
  if (base.includes(rootId)) {
    const next = base.filter((id) => id !== rootId);
    return next.length > 0 ? next : base;
  }
  return [...base, rootId];
}
