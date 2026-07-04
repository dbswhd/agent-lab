import { describe, expect, it } from "vitest";
import {
  emergenceHintLine,
  FALLBACK_ROOM_PRESETS,
  fastRosterOverflow,
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
    expect(presetHintLine(FALLBACK_ROOM_PRESETS[1], "en")).toContain("Emergence");
  });

  it("shows recombination skip in emergence hint", () => {
    const hint = emergenceHintLine(
      {
        room_preset: "supervisor",
        consensus: { recombination: { skipped: "efficiency" } },
      },
      "ko",
    );
    expect(hint).toContain("재조합");
  });

  it("detects fast roster overflow (§3.2.1)", () => {
    expect(fastRosterOverflow("fast", 2)).toBe(true);
    expect(fastRosterOverflow("fast", 1)).toBe(false);
    expect(fastRosterOverflow("supervisor", 3)).toBe(false);
  });

  it("hints light discuss and fast promotion", () => {
    expect(
      emergenceHintLine({ room_preset: "supervisor", discuss_light: true }, "en"),
    ).toContain("full-parallel");
    expect(
      emergenceHintLine(
        { room_preset: "supervisor", room_preset_promoted_from: "fast" },
        "ko",
      ),
    ).toContain("승격");
  });
});
