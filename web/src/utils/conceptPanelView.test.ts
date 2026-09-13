import { describe, expect, it } from "vitest";
import { buildCandidateRows, canRequestPlan, stageView } from "./conceptPanelView";

const base = {
  schema_version: 1,
  revision: 2,
  stage: "shape" as const,
  options: [
    {
      id: "opt-ready",
      title: "준비된 방향",
      quality: { status: "ready" },
    },
    {
      id: "opt-review",
      title: "검토할 방향",
      quality: { status: "needs_review", unverified_repo_claims: ["claim"] },
    },
  ],
  selection: { option_id: "opt-ready" },
};

describe("concept panel quality gate", () => {
  it("allows an explicit plan request only for a ready selection", () => {
    expect(canRequestPlan(base)).toBe(true);
    expect(canRequestPlan({ ...base, selection: { option_id: "opt-review" } })).toBe(false);
    expect(canRequestPlan({ ...base, plan_status: "ready" })).toBe(false);
  });

  it("keeps review state visible on candidate rows", () => {
    const rows = buildCandidateRows(base);
    expect(rows[1].qualityStatus).toBe("needs_review");
    expect(rows[1].qualityMessage).toContain("검토 필요");
  });

  it("does not label a failed or pending plan as ready", () => {
    expect(stageView({ ...base, stage: "plan", plan_status: "failed" })?.label).toBe("계획 생성 실패");
    expect(stageView({ ...base, stage: "plan", plan_status: "pending" })?.label).toBe("계획 준비 중");
    expect(stageView({ ...base, stage: "plan", plan_status: "ready" })?.label).toBe("계획 준비됨");
  });
});
