import { describe, expect, it, beforeEach } from "vitest";
import {
  getSessionRunSnapshot,
  resetTurnRun,
  syncSessionFromServerLock,
  updateSessionRun,
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
