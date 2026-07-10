import { describe, expect, it } from "vitest";
import { isDogfoodSession } from "./dogfoodSessions";
import type { SessionSummary } from "../api/client";

function session(overrides: Partial<SessionSummary>): SessionSummary {
  return { id: "s1", topic: "", ...overrides };
}

describe("isDogfoodSession", () => {
  it("matches topics mentioning dogfood", () => {
    expect(
      isDogfoodSession(session({ topic: "N4 dogfood 세션 시작" })),
    ).toBe(true);
  });

  it("matches x2-lift topics regardless of separator", () => {
    expect(isDogfoodSession(session({ topic: "x2 lift execute fixture" }))).toBe(
      true,
    );
    expect(isDogfoodSession(session({ topic: "x2lift retry" }))).toBe(true);
  });

  it("matches the S1 consensus round-cap fixture topic", () => {
    expect(
      isDogfoodSession(session({ topic: "consensus 라운드 cap 기본값 관측" })),
    ).toBe(true);
  });

  it("matches on session id when topic does not carry the pattern", () => {
    expect(
      isDogfoodSession(session({ id: "2026-07-10-dogfood-run", topic: "" })),
    ).toBe(true);
  });

  it("does not match ordinary session topics", () => {
    expect(
      isDogfoodSession(session({ topic: "refactor the plan approve flow" })),
    ).toBe(false);
  });
});
