import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  SESSION_GROUP_UNGROUPED_LABEL,
  createSessionGroup,
  groupSessionsForDrag,
  groupSessionsForList,
  isSessionPinned,
  moveSessionToGroup,
  toggleSessionPinned,
} from "./sessionGroupPrefs";
import type { SessionSummary } from "../api/client";

const STORAGE_KEY = "agent-lab-session-groups";

function session(id: string, topic: string, created_at?: string): SessionSummary {
  return { id, topic, created_at };
}

describe("sessionGroupPrefs", () => {
  beforeEach(() => {
    const bag = new Map<string, string>();
    vi.stubGlobal("localStorage", {
      getItem: (key: string) => bag.get(key) ?? null,
      setItem: (key: string, value: string) => {
        bag.set(key, value);
      },
      removeItem: (key: string) => {
        bag.delete(key);
      },
      clear: () => {
        bag.clear();
      },
    });
    localStorage.removeItem(STORAGE_KEY);
  });

  it("creates groups and assigns sessions", () => {
    createSessionGroup("agent lab");
    moveSessionToGroup("s1", "agent lab");
    const grouped = groupSessionsForList([
      session("s1", "One"),
      session("s2", "Two"),
    ]);
    expect(grouped).toHaveLength(2);
    expect(grouped[0]?.label).toBe("agent lab");
    expect(grouped[0]?.sessions.map((s) => s.id)).toEqual(["s1"]);
    expect(grouped[1]?.label).toBe(SESSION_GROUP_UNGROUPED_LABEL);
    expect(grouped[1]?.sessions.map((s) => s.id)).toEqual(["s2"]);
  });

  it("pins sessions ahead of recency sort", () => {
    toggleSessionPinned("old");
    const grouped = groupSessionsForList([
      session("new", "New", "2026-06-29T12:00:00Z"),
      session("old", "Old", "2026-06-01T12:00:00Z"),
    ]);
    expect(grouped[0]?.sessions.map((s) => s.id)).toEqual(["old", "new"]);
    expect(isSessionPinned("old")).toBe(true);
    toggleSessionPinned("old");
    expect(isSessionPinned("old")).toBe(false);
  });

  it("surfaces empty named groups while dragging", () => {
    createSessionGroup("agent lab");
    const grouped = groupSessionsForDrag([session("s2", "Two")]);
    expect(grouped.map((group) => group.key)).toEqual([
      "agent lab",
      SESSION_GROUP_UNGROUPED_LABEL,
    ]);
    expect(grouped[0]?.sessions).toEqual([]);
  });
});
