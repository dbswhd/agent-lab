import { describe, expect, it } from "vitest";
import type { MissionReadModelPayload } from "../api/client";
import { missionReadModelPhase } from "./missionOverviewView";

const payload = {
  session_id: "s1",
  migrated: true,
  source: "mission_journal",
  mission_id: "m1",
  goal: "ship",
  state: "EXECUTING",
  version: 1,
  plan_revision: 1,
  plan_hash: null,
  approved_plan_hash: null,
  repair_attempt: 0,
  max_repair_attempts: 2,
  oracle_verdict: null,
  next_action: "observe_execution",
  event_cursor: 1,
  operational_status: "RUNNING",
  open_execution_gates: [],
  legacy_phase: null,
  mission_overview: {
    phase_label: "MISSION_PAUSED",
    paused: true,
    circuit_breaker: true,
    pending_inbox_count: 0,
  },
} satisfies MissionReadModelPayload;

describe("missionReadModelPhase", () => {
  it("uses the localized projection phase before the kernel state", () => {
    expect(missionReadModelPhase(payload)).toBe("MISSION_PAUSED");
  });
});
