import { describe, expect, it } from "vitest";
import {
  autonomyLevelLabel,
  buildAutonomySessionView,
} from "./autonomyLadder";

describe("autonomyLadder", () => {
  it("labels levels in ko and en", () => {
    expect(autonomyLevelLabel("L0", "ko")).toBe("수동");
    expect(autonomyLevelLabel("L3", "en")).toBe("Autonomous");
  });

  it("builds summary with trust budget", () => {
    const view = buildAutonomySessionView(
      {
        level: "L2",
        effective_level: "L2",
        display_level: "L2",
        level_name: "Budgeted",
        trust_budget: { auto_merge_remaining: 2, auto_merge_total: 5 },
        signals: {
          auto_approve_enabled: false,
          mission_loop_enabled: true,
          autonomous_segment_active: false,
        },
      },
      "en",
    );
    expect(view?.summary).toContain("trust 2/5");
  });
});
