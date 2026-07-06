import { describe, expect, it, beforeEach } from "vitest";
import {
  getSessionRunSnapshot,
  finishSessionRun,
  hydrateSessionMessages,
  resetTurnRun,
  syncSessionFromServerLock,
  syncRunStateFromLiveLog,
  updateSessionRun,
  type LiveMsg,
} from "./runSessionRegistry";

describe("runSessionRegistry localSseRun", () => {
  const sid = "test-session-local-sse";

  beforeEach(() => {
    updateSessionRun(sid, {
      messages: [],
      turnMessages: [],
      running: false,
      runBusy: false,
      localSseRun: false,
      runStartedAt: null,
      topologyActive: null,
      topologyDone: new Set(),
    });
  });

  it("does not clear running while localSseRun is active and lock is idle", () => {
    resetTurnRun(sid, {
      id: "u1",
      role: "you",
      label: "You",
      body: "hello",
      sent: true,
    });
    expect(getSessionRunSnapshot(sid).localSseRun).toBe(true);
    expect(getSessionRunSnapshot(sid).running).toBe(true);

    syncSessionFromServerLock({ locked: false });

    const snap = getSessionRunSnapshot(sid);
    expect(snap.localSseRun).toBe(true);
    expect(snap.running).toBe(true);
  });

  it("clears orphaned running when lock idle and no local SSE turn", () => {
    updateSessionRun(sid, {
      running: true,
      runBusy: true,
      localSseRun: false,
      backgroundRun: { runKind: "room", label: "Running" },
    });

    syncSessionFromServerLock({ locked: false });

    const snap = getSessionRunSnapshot(sid);
    expect(snap.running).toBe(false);
    expect(snap.runBusy).toBe(false);
    expect(snap.backgroundRun).toBeNull();
  });
});

describe("hydrateSessionMessages", () => {
  const sid = "test-hydrate-turn-items";

  function firstTurnItemText(message: LiveMsg | undefined): string | undefined {
    const item = message?.turnItems?.[0];
    if (!item || item.kind === "tool") return undefined;
    return item.text;
  }

  beforeEach(() => {
    updateSessionRun(sid, {
      messages: [],
      turnMessages: [],
      running: false,
      runBusy: false,
      localSseRun: false,
      runStartedAt: null,
      topologyActive: null,
      topologyDone: new Set(),
    });
  });

  it("preserves local turnItems when server chat hydrates without activity", () => {
    updateSessionRun(sid, {
      messages: [
        { id: "u1", role: "you", label: "You", body: "hello", sent: true },
        {
          id: "c1",
          role: "codex",
          label: "Codex",
          body: "done",
          parallelRound: 1,
          turnItems: [
            { id: "t1", kind: "activity", text: "Reading repo", status: "done" },
          ],
        },
      ],
    });
    hydrateSessionMessages(sid, [
      { id: "u1", role: "you", label: "You", body: "hello", sent: true },
      {
        id: "s-c1",
        role: "codex",
        label: "Codex",
        body: "done from server",
        parallelRound: 1,
      },
    ]);
    const codex = getSessionRunSnapshot(sid).messages.find((m) => m.role === "codex");
    expect(codex?.turnItems?.some((item) => item.kind === "activity")).toBe(true);
  });

  it("clears typing on finish without deleting activity-only rows", () => {
    updateSessionRun(sid, {
      messages: [
        {
          id: "typing-codex-r1",
          role: "codex",
          label: "Codex",
          body: "",
          typing: true,
          parallelRound: 1,
          turnItems: [
            { id: "t1", kind: "activity", text: "Reading repo", status: "done" },
          ],
        },
      ],
      turnMessages: [
        {
          id: "typing-codex-r1",
          role: "codex",
          label: "Codex",
          body: "",
          typing: true,
          parallelRound: 1,
          turnItems: [
            { id: "t1", kind: "activity", text: "Reading repo", status: "done" },
          ],
        },
      ],
      running: true,
      runBusy: true,
      localSseRun: true,
    });

    finishSessionRun(sid);

    const snap = getSessionRunSnapshot(sid);
    const codex = snap.messages.find((m) => m.role === "codex");
    expect(snap.running).toBe(false);
    expect(codex?.typing).toBe(false);
    expect(firstTurnItemText(codex)).toBe("Reading repo");
  });
});

describe("syncRunStateFromLiveLog", () => {
  const sid = "test-sync-live-log";

  beforeEach(() => {
    updateSessionRun(sid, {
      messages: [],
      turnMessages: [],
      running: false,
      runBusy: false,
      localSseRun: false,
      runStartedAt: null,
      topologyActive: null,
      topologyDone: new Set(),
    });
  });

  it("marks session running when live log has open agent turns", () => {
    syncRunStateFromLiveLog(sid, [
      { type: "agent_start", agent: "codex", round: 1, ts: "2026-07-02T10:00:00.000Z" },
    ]);
    const snap = getSessionRunSnapshot(sid);
    expect(snap.running).toBe(true);
    expect(snap.localSseRun).toBe(true);
    expect(snap.runStartedAt).toBe(Date.parse("2026-07-02T10:00:00.000Z"));
  });
});
