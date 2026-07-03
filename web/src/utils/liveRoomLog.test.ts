import { describe, expect, it } from "vitest";
import { inferRunStateFromLiveLog } from "./liveRoomLog";

describe("inferRunStateFromLiveLog", () => {
  it("detects open agent turns before agent_done", () => {
    const state = inferRunStateFromLiveLog([
      { type: "agent_start", agent: "codex", round: 1, ts: "2026-07-02T10:00:00.000Z" },
      { type: "agent_activity", agent: "codex", round: 1, text: "Reading repo" },
    ]);
    expect(state.inFlight).toBe(true);
    expect(state.runStartedAt).toBe(Date.parse("2026-07-02T10:00:00.000Z"));
  });

  it("returns idle after agent_done", () => {
    const state = inferRunStateFromLiveLog([
      { type: "agent_start", agent: "codex", round: 1 },
      { type: "agent_done", agent: "codex", round: 1, content: "ok" },
    ]);
    expect(state.inFlight).toBe(false);
  });
});
