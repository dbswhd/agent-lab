import { describe, expect, it } from "vitest";
import {
  autonomyLevelCards,
  autonomyLevelLabel,
  autonomyWhyStopped,
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
    // The summary is a sentence a human reads, not a ledger line.
    expect(view?.needsYou).toBe(false);
    expect(view?.statusLabel).toBe("Can go alone");
    expect(view?.statusDetail).toBe("2/5 auto-continues left");
    expect(view?.summary).toBe("Can go alone. 2/5 auto-continues left");
  });

  it("includes recent transitions for demotion UI", () => {
    const view = buildAutonomySessionView(
      {
        level: "L0",
        effective_level: "L0",
        display_level: "L0",
        level_name: "Manual",
        ceiling_set: true,
        trust_budget: { auto_merge_remaining: 0, auto_merge_total: 1 },
        signals: {
          auto_approve_enabled: false,
          mission_loop_enabled: false,
          autonomous_segment_active: false,
        },
        transitions: [
          {
            from: "L2",
            to: "L0",
            trigger: "demotion",
            reason: "trust_budget_consumed",
          },
        ],
      },
      "en",
    );
    expect(view?.transitions).toHaveLength(1);
    expect(view?.transitions[0]?.trigger).toBe("demotion");
    // …and the demotion is explained rather than shown as a reason code.
    expect(view?.needsYou).toBe(true);
    expect(view?.whyStopped).toBe("The auto-continue budget ran out.");
    expect(view?.summary).toContain("The auto-continue budget ran out.");
    expect(view?.summary).not.toContain("trust_budget_consumed");
  });

  it("explains each demotion reason in plain language", () => {
    expect(autonomyWhyStopped("trust_budget_consumed", "en")).toBe(
      "The auto-continue budget ran out.",
    );
    expect(autonomyWhyStopped("oracle_fail_consecutive", "en")).toBe(
      "Verification (Oracle) failed repeatedly.",
    );
    expect(autonomyWhyStopped("diff_risk_high", "en")).toBe(
      "The change was classified as high risk.",
    );
    expect(autonomyWhyStopped("quarter_budget_usd", "en")).toBe(
      "The quarterly spend limit was hit.",
    );
    expect(autonomyWhyStopped("risk_pin_trading", "ko")).toContain("트레이딩");
    expect(autonomyWhyStopped("inbox_restore_ceiling", "ko")).toBe(
      "이전 설정을 다시 켰습니다.",
    );
  });

  it("falls through unknown reasons without leaking level tokens", () => {
    expect(autonomyWhyStopped("L2 something odd L0", "en")).toBe(
      "something odd",
    );
    expect(autonomyWhyStopped("", "en")).toBe("Auto-run was turned down.");
    expect(autonomyWhyStopped(null, "ko")).toBe("자동 진행이 꺼졌습니다.");
  });

  it("describes every rung by what it lets the agents do", () => {
    const cards = autonomyLevelCards("en");
    expect(cards.map((c) => c.level)).toEqual(["L0", "L1", "L2", "L3"]);
    expect(cards[0]?.title).toBe("Ask me each time");
    expect(cards[3]?.title).toBe("Run the mission");
    // no rung is described by its code name alone
    for (const card of cards) {
      expect(card.title).not.toMatch(/^L[0-3]$/);
      expect(card.hint.length).toBeGreaterThan(10);
    }
  });
});
