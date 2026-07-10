import { describe, expect, it } from "vitest";
import { buildRoutingDiagnostics } from "./routingDiagnostics";

describe("buildRoutingDiagnostics", () => {
  it("keeps routing internals available for the diagnostics disclosure", () => {
    expect(
      buildRoutingDiagnostics(
        {
          agents: ["cursor", "codex"],
          consensus_mode: true,
          turn_contract: {
            contract_id: "guarded_plan",
            source: "bootstrap",
          },
        },
        "balanced",
      ),
    ).toEqual({
      route: "guarded_plan",
      source: "bootstrap",
      agents: ["cursor", "codex"],
      consensus: true,
      runProfile: "balanced",
    });
  });

  it("falls back to policy routing without leaking invalid values", () => {
    expect(
      buildRoutingDiagnostics({
        agents: ["codex", null, ""],
        turn_policy: {
          routing_contract: { route_category: "quick" },
          scribe_trigger: "none",
        },
      }),
    ).toEqual({
      route: "quick",
      source: "none",
      agents: ["codex"],
      consensus: false,
      runProfile: "—",
    });
  });
});
