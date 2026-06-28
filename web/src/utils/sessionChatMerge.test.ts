import { describe, expect, it } from "vitest";
import {
  mergePersistedChatWithLiveLog,
  preferRicherChatMessages,
} from "./sessionChatMerge";
import type { LiveMsg } from "../run/runSessionRegistry";

const label = (id: string) => id;

describe("mergePersistedChatWithLiveLog", () => {
  it("appends live agent replies missing from persisted chat", () => {
    const chat: LiveMsg[] = [
      { id: "u1", role: "you", label: "You", body: "hello" },
      {
        id: "c1",
        role: "cursor",
        label: "Cursor",
        body: "cursor ok",
        parallelRound: 1,
      },
    ];
    const live = [
      { type: "agent_start", agent: "codex", round: 1 },
      {
        type: "agent_done",
        agent: "codex",
        round: 1,
        content: "codex partial",
      },
    ];
    const merged = mergePersistedChatWithLiveLog(chat, live, label);
    expect(merged).toHaveLength(3);
    expect(merged[2]?.role).toBe("codex");
    expect(merged[2]?.body).toContain("codex partial");
  });

  it("skips duplicate agent rounds already in chat", () => {
    const chat: LiveMsg[] = [
      {
        id: "c1",
        role: "cursor",
        label: "Cursor",
        body: "done",
        parallelRound: 1,
      },
    ];
    const live = [
      {
        type: "agent_done",
        agent: "cursor",
        round: 1,
        content: "done",
      },
    ];
    expect(mergePersistedChatWithLiveLog(chat, live, label)).toEqual(chat);
  });
});

describe("preferRicherChatMessages", () => {
  it("keeps local when it has more rows", () => {
    const local: LiveMsg[] = [
      { id: "1", role: "you", label: "You", body: "a" },
      { id: "2", role: "cursor", label: "Cursor", body: "b" },
    ];
    const server: LiveMsg[] = [{ id: "1", role: "you", label: "You", body: "a" }];
    expect(preferRicherChatMessages(local, server)).toBe(local);
  });
});
