import { describe, expect, it } from "vitest";
import { turnProfileForRoomPreset } from "./roomComposerPrefs";

describe("roomComposerPrefs", () => {
  it("maps fast/supervisor presets to turn profiles", () => {
    expect(turnProfileForRoomPreset("fast")).toBe("quick");
    expect(turnProfileForRoomPreset("supervisor")).toBe("loop");
    expect(turnProfileForRoomPreset("other")).toBeNull();
    expect(turnProfileForRoomPreset(null)).toBeNull();
  });
});
