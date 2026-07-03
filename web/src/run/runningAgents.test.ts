import { describe, expect, it } from "vitest";
import { derivePendingReplyAgents } from "./runningAgents";
import type { LiveMsg } from "./runSessionRegistry";

describe("derivePendingReplyAgents", () => {
  it("returns no placeholders when typing bubbles exist", () => {
    const messages: LiveMsg[] = [
      {
        id: "typing-codex-r1",
        role: "codex",
        label: "Codex",
        body: "",
        typing: true,
      },
    ];
    expect(
      derivePendingReplyAgents(messages, {
        running: true,
        expectedAgents: ["codex", "claude"],
        topologyActive: null,
        topologyDone: new Set(),
      }),
    ).toEqual([]);
  });

  it("shows only topologyActive agent after peers finish", () => {
    expect(
      derivePendingReplyAgents([], {
        running: true,
        expectedAgents: ["codex", "claude", "kimi_work"],
        topologyActive: { agent: "codex", round: 1 },
        topologyDone: new Set(["claude:1", "kimi_work:1"]),
      }),
    ).toEqual([
      {
        id: "pending-codex-r1",
        role: "codex",
        label: "Codex",
      },
    ]);
  });

  it("shows nothing before the first agent_start SSE", () => {
    expect(
      derivePendingReplyAgents([], {
        running: true,
        expectedAgents: ["codex", "claude"],
        topologyActive: null,
        topologyDone: new Set(),
      }),
    ).toEqual([]);
  });

  it("shows @-mention targets before the first agent_start SSE", () => {
    expect(
      derivePendingReplyAgents([], {
        running: true,
        mentionFiltered: true,
        expectedAgents: ["codex"],
        topologyActive: null,
        topologyDone: new Set(),
      }),
    ).toEqual([
      {
        id: "pending-codex-r1",
        role: "codex",
        label: "Codex",
      },
    ]);
  });

  it("shows remaining agents once some have finished", () => {
    expect(
      derivePendingReplyAgents([], {
        running: true,
        expectedAgents: ["codex", "claude"],
        topologyActive: null,
        topologyDone: new Set(["claude:1"]),
      }),
    ).toEqual([
      {
        id: "pending-codex-r1",
        role: "codex",
        label: "Codex",
      },
    ]);
  });
});
