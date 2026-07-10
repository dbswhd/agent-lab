import { describe, expect, it } from "vitest";
import { workStepStatusClass } from "./workStepClass";

describe("workStepStatusClass", () => {
  it("marks active and completed steps", () => {
    expect(workStepStatusClass(1, 1)).toBe("is-active");
    expect(workStepStatusClass(0, 1)).toBe("is-done");
    expect(workStepStatusClass(2, 1)).toBe("");
  });

  it("marks every step done when markAllDone is set", () => {
    expect(workStepStatusClass(0, 5, { markAllDone: true })).toBe("is-done");
    expect(workStepStatusClass(4, 5, { markAllDone: true })).toBe("is-done");
  });
});
