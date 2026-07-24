import { describe, expect, it } from "vitest";
import { buildExecuteEvidenceStrip } from "./executeEvidenceStrip";

describe("buildExecuteEvidenceStrip", () => {
  it("summarizes diff, checks, and oracle for the Decision Queue", () => {
    const strip = buildExecuteEvidenceStrip(
      {
        id: "e1",
        diff_stat: "2 files changed, 10 insertions(+)",
        touched_paths: ["a.ts", "b.ts"],
        oracle: { verdict: "pass" },
        oracle_verdict: "pass",
      },
      {
        checks: [
          { id: "clean", ok: true },
          { id: "tests", ok: true },
          { id: "lint", ok: false },
        ],
        merge_disabled: false,
      },
    );
    expect(strip.diffLabel).toContain("2 files changed");
    expect(strip.checksLabel).toBe("Checks 2/3");
    expect(strip.oracleLabel).toBe("Oracle pass");
    expect(strip.oracleTone).toBe("pass");
  });
});
