import { describe, expect, it } from "vitest";
import { planComposeActive, turnProfileForRoomPreset } from "./roomComposerPrefs";

describe("roomComposerPrefs", () => {
  it("maps fast/supervisor presets to turn profiles", () => {
    expect(turnProfileForRoomPreset("fast")).toBe("quick");
    expect(turnProfileForRoomPreset("supervisor")).toBe("loop");
    expect(turnProfileForRoomPreset("other")).toBeNull();
    expect(turnProfileForRoomPreset(null)).toBeNull();
  });

  it("detects plan compose mode from preset or loop profile", () => {
    expect(planComposeActive("supervisor", "quick")).toBe(true);
    expect(planComposeActive("fast", "loop")).toBe(true);
    expect(planComposeActive("fast", "quick")).toBe(false);
  });
});
