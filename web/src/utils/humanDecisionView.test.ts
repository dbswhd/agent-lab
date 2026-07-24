import { describe, expect, it } from "vitest";
import { buildHumanDecisionLanes } from "./humanDecisionView";
import type { RuntimeSnapshot } from "../api/client";

function runtimeWithDiscussOpen(open: boolean): RuntimeSnapshot {
  return {
    gates: { discuss: { open } },
  } as unknown as RuntimeSnapshot;
}

describe("buildHumanDecisionLanes", () => {
  it("stays blocked while discussPaused is true and the gate hasn't reopened yet", () => {
    const lanes = buildHumanDecisionLanes(null, true);
    expect(lanes.find((l) => l.id === "discuss")?.blocked).toBe(true);
  });

  it("clears a stale discussPaused flag once the server confirms the gate is open", () => {
    // Reproduces the stuck "Discuss blocked: pending question" banner: a
    // different tab/session resolves the Human Inbox item, so this tab's
    // local discussPaused state never flips back to false on its own —
    // but a fresh runtime snapshot should win over it.
    const lanes = buildHumanDecisionLanes(runtimeWithDiscussOpen(true), true);
    expect(lanes.find((l) => l.id === "discuss")?.blocked).toBe(false);
  });

  it("stays blocked when the server explicitly reports the gate closed", () => {
    const lanes = buildHumanDecisionLanes(runtimeWithDiscussOpen(false), false);
    expect(lanes.find((l) => l.id === "discuss")?.blocked).toBe(true);
  });
});
