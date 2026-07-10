import { describe, expect, it } from "vitest";
import { WORK_PHASE_LABELS, workPhaseLabel } from "./workPhaseLabels";

describe("workPhaseLabel", () => {
  it("uses outcome-oriented Korean labels for every phase", () => {
    expect(WORK_PHASE_LABELS.map((step) => step.ko)).toEqual([
      "실행 준비",
      "실행 검토",
      "변경 중",
      "변경 검토",
      "검증 완료",
    ]);
  });

  it("localizes the compact phase label", () => {
    expect(workPhaseLabel("merge_verify", "ko")).toBe("변경 검토");
    expect(workPhaseLabel("merge_verify", "en")).toBe("Review changes");
  });
});
