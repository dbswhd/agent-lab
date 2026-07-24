import { describe, expect, it } from "vitest";
import { buildSessionStatusChips } from "./sessionStatusLine";

describe("buildSessionStatusChips", () => {
  it("includes F8 cost chip with warn tone", () => {
    const chips = buildSessionStatusChips({
      locale: "en",
      session: {
        id: "s1",
        topic: "t",
        cost: {
          budget: { spent_usd: 4.2, limit_usd: 5, warn: true, over: false },
        },
      } as never,
    });
    const cost = chips.find((c) => c.id === "cost");
    expect(cost?.label).toContain("$4.20");
    expect(cost?.tone).toBe("warn");
  });

  it("includes waiting chip when human gate is open", () => {
    const chips = buildSessionStatusChips({
      locale: "en",
      runtime: {
        status_line: {
          human_gate_opened_at: "2026-07-24T10:00:00Z",
          human_gate_kind: "plan_approval",
        },
      } as never,
    });
    expect(chips.some((c) => c.id === "human_gate")).toBe(true);
  });
});
