import { describe, expect, it } from "vitest";

import { resolveGjcPipelinePhase } from "./gjcPipelinePhase";

describe("resolveGjcPipelinePhase", () => {
  it("maps HUMAN_PENDING to approve", () => {
    expect(
      resolveGjcPipelinePhase({
        hasPlan: true,
        planWorkflow: { phase: "HUMAN_PENDING" },
      }),
    ).toBe("approve");
  });

  it("maps PEER_REVIEW to plan", () => {
    expect(
      resolveGjcPipelinePhase({
        hasPlan: true,
        planWorkflow: { phase: "PEER_REVIEW" },
      }),
    ).toBe("plan");
  });

  it("maps oracle pass to done", () => {
    expect(
      resolveGjcPipelinePhase({
        hasPlan: true,
        latestExecution: {
          id: "exec-1",
          status: "completed",
          oracle: { verdict: "pass" },
        },
      }),
    ).toBe("done");
  });

  it("maps CLARIFY to interview", () => {
    expect(
      resolveGjcPipelinePhase({
        hasPlan: false,
        planWorkflow: { phase: "CLARIFY" },
      }),
    ).toBe("interview");
  });
});
