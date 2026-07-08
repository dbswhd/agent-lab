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

  it("merges turn activity from live_log into persisted chat rows", () => {
    const chat: LiveMsg[] = [
      { id: "u1", role: "you", label: "You", body: "hello" },
      {
        id: "c1",
        role: "kimi_work",
        label: "Kimi Work",
        body: "final reply",
        parallelRound: 1,
      },
    ];
    const live = [
      { type: "agent_start", agent: "kimi_work", round: 1 },
      {
        type: "agent_activity",
        agent: "kimi_work",
        round: 1,
        text: "[net] kimi-work:k2p6 daimon/conversations.send",
      },
      {
        type: "agent_done",
        agent: "kimi_work",
        round: 1,
        content: "final reply",
      },
    ];
    const merged = mergePersistedChatWithLiveLog(chat, live, label);
    const kimi = merged.find((m) => m.role === "kimi_work");
    expect(kimi?.turnItems?.some((item) => item.kind === "activity")).toBe(
      true,
    );
    expect(merged).toHaveLength(2);
  });

  it("does not replay typing for cancelled system agent rows", () => {
    const chat: LiveMsg[] = [
      {
        id: "s-codex",
        role: "system",
        label: "Codex",
        body: "_(취소됨)_",
        parallelRound: 1,
        sourceAgent: "codex",
      },
    ];
    const live = [{ type: "agent_start", agent: "codex", round: 1 }];
    const merged = mergePersistedChatWithLiveLog(chat, live, label);
    expect(merged).toHaveLength(1);
    expect(merged[0]?.typing).toBeUndefined();
  });

  it("restores in-flight typing shells from live_log on refresh", () => {
    const chat: LiveMsg[] = [
      { id: "u1", role: "you", label: "You", body: "@codex ping", sent: true },
    ];
    const live = [{ type: "agent_start", agent: "codex", round: 1 }];
    const merged = mergePersistedChatWithLiveLog(chat, live, label);
    expect(merged).toHaveLength(2);
    expect(merged[1]?.role).toBe("codex");
    expect(merged[1]?.typing).toBe(true);
  });
});

describe("preferRicherChatMessages", () => {
  it("keeps local when it has more rows", () => {
    const local: LiveMsg[] = [
      { id: "1", role: "you", label: "You", body: "a" },
      { id: "2", role: "cursor", label: "Cursor", body: "b" },
    ];
    const server: LiveMsg[] = [
      { id: "1", role: "you", label: "You", body: "a" },
    ];
    expect(preferRicherChatMessages(local, server)).toBe(local);
  });

  it("keeps the local activity trail when the server transcript wins", () => {
    const local: LiveMsg[] = [
      { id: "u1", role: "you", label: "You", body: "hello" },
      {
        id: "c1",
        role: "cursor",
        label: "Cursor",
        body: "short",
        parallelRound: 1,
        turnItems: [
          { id: "t1", kind: "activity", text: "Reading repo", status: "done" },
        ],
      },
    ];
    // Server refetch after completion — same turn, longer persisted body,
    // but it never carries the tool/thought trail (chat.jsonl doesn't store it).
    const server: LiveMsg[] = [
      { id: "s-u1", role: "you", label: "You", body: "hello" },
      {
        id: "s-c1",
        role: "cursor",
        label: "Cursor",
        body: "a much longer finalized reply body",
        parallelRound: 1,
      },
    ];
    const merged = preferRicherChatMessages(local, server);
    expect(merged).toHaveLength(server.length);
    const cursorMsg = merged.find((m) => m.role === "cursor");
    expect(cursorMsg?.turnItems).toEqual(local[1]?.turnItems);
    expect(cursorMsg?.body).toBe("a much longer finalized reply body");
  });
});
