import { useCallback, useRef, useState } from "react";
import { listWorkspaceFileRoots, listWorkspaceFiles } from "../api/client";

const MAX_PATHS = 120;

export async function collectMentionPaths(sessionId: string): Promise<string[]> {
  const { roots } = await listWorkspaceFileRoots(sessionId);
  const out: string[] = [];

  async function walk(rootId: string, dir: string, depth: number): Promise<void> {
    if (out.length >= MAX_PATHS || depth > 3) return;
    const res = await listWorkspaceFiles(sessionId, rootId, dir);
    for (const entry of res.entries) {
      if (out.length >= MAX_PATHS) break;
      const path = dir ? `${dir}/${entry.name}` : entry.name;
      if (entry.type === "file") {
        out.push(path);
      } else {
        await walk(rootId, path, depth + 1);
      }
    }
  }

  for (const root of roots) {
    if (root.missing) continue;
    try {
      await walk(root.root_id, "", 0);
    } catch {
      /* skip unreadable roots */
    }
  }
  return out;
}

export function useComposerMentionPaths(sessionId: string | null | undefined) {
  const [paths, setPaths] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const loadedRef = useRef(false);

  const ensureLoaded = useCallback(async () => {
    if (!sessionId || loadedRef.current || loading) return;
    setLoading(true);
    try {
      const next = await collectMentionPaths(sessionId);
      setPaths(next);
      loadedRef.current = true;
    } catch {
      setPaths([]);
    } finally {
      setLoading(false);
    }
  }, [sessionId, loading]);

  return { paths, loading, ensureLoaded };
}

export function mentionQueryAtCursor(value: string, cursor: number): string | null {
  const head = value.slice(0, cursor);
  const match = head.match(/(?:^|\s)@([^\s@]*)$/);
  return match ? match[1] : null;
}
