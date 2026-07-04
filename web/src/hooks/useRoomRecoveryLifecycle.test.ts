import { describe, expect, it } from "vitest";
import {
  discussRecoveryFromMissionLoop,
  type DiscussRecoveryState,
} from "./useRoomRecoveryLifecycle";
import { turnProfileForRoomPreset } from "../utils/roomComposerPrefs";

describe("discussRecoveryFromMissionLoop", () => {
  it("returns null when mission loop is missing", () => {
    expect(discussRecoveryFromMissionLoop(undefined)).toBeNull();
    expect(discussRecoveryFromMissionLoop(null)).toBeNull();
  });

  it("extracts discuss_recovery payload", () => {
    const state: DiscussRecoveryState = {
      pending: true,
      reason: "stalled",
      action_index: 2,
    };
    expect(
      discussRecoveryFromMissionLoop({ discuss_recovery: state }),
    ).toEqual(state);
  });
});

describe("turnProfileForRoomPreset", () => {
  it("maps fast and supervisor presets", () => {
    expect(turnProfileForRoomPreset("fast")).toBe("quick");
    expect(turnProfileForRoomPreset("supervisor")).toBe("loop");
    expect(turnProfileForRoomPreset("other")).toBeNull();
  });
});
