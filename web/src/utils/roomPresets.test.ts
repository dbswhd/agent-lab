import { describe, expect, it } from "vitest";
import {
  FALLBACK_ROOM_PRESETS,
  presetDisplayLabel,
  presetHintLine,
  resolveRoomPresets,
} from "./roomPresets";

describe("roomPresets", () => {
  it("falls back to fast and supervisor when API list is empty", () => {
    expect(resolveRoomPresets([]).map((p) => p.id)).toEqual(["fast", "supervisor"]);
  });

  it("labels presets for ko locale", () => {
    expect(presetDisplayLabel(FALLBACK_ROOM_PRESETS[0], "ko")).toBe("빠른");
    expect(presetDisplayLabel(FALLBACK_ROOM_PRESETS[1], "ko")).toBe("감독");
  });

  it("returns localized hint lines", () => {
    expect(presetHintLine(FALLBACK_ROOM_PRESETS[0], "ko")).toContain("에이전트 1명");
    expect(presetHintLine(FALLBACK_ROOM_PRESETS[1], "en")).toContain("consensus");
  });
});
