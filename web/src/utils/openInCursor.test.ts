import { describe, expect, it } from "vitest";
import { cursorFileUri } from "./openInCursor";

describe("cursorFileUri", () => {
  it("builds a cursor://file URI for absolute paths", () => {
    expect(cursorFileUri("/Users/me/proj")).toBe("cursor://file/Users/me/proj");
  });

  it("returns empty for blank input", () => {
    expect(cursorFileUri("  ")).toBe("");
  });
});
