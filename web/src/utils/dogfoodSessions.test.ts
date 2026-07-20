import { describe, expect, it } from "vitest";
import { isDogfoodSession } from "./dogfoodSessions";
import type { SessionSummary } from "../api/client";

function session(overrides: Partial<SessionSummary>): SessionSummary {
  return { id: "s1", topic: "", ...overrides };
}

describe("isDogfoodSession", () => {
  it("matches topics mentioning dogfood", () => {
    expect(isDogfoodSession(session({ topic: "N4 dogfood 세션 시작" }))).toBe(
      true,
    );
  });

  it("matches x2-lift topics regardless of separator", () => {
    expect(
      isDogfoodSession(session({ topic: "x2 lift execute fixture" })),
    ).toBe(true);
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

  it("does not match ordinary (Korean) session topics", () => {
    expect(
      isDogfoodSession(
        session({
          id: "2026-07-20-agent-lab의-개발-방향에-대해-논의해보자",
          topic: "agent-lab의 개발 방향에 대해 논의해보자",
        }),
      ),
    ).toBe(false);
  });

  it("matches [cat: quick|standard|deep] catalog-tagged topics, bracketed or slugified", () => {
    expect(
      isDogfoodSession(
        session({
          topic:
            "docs/README.md Tier 1 표에 깨진 링크가 있는지 확인해줘 [cat: quick]",
        }),
      ),
    ).toBe(true);
    expect(
      isDogfoodSession(
        session({ id: "2026-07-07-docsreadmemd-tier-1-cat-quick", topic: "" }),
      ),
    ).toBe(true);
  });

  it("matches the pre-x2-lift '오타 1건 수정 plan action' fixture wording", () => {
    expect(
      isDogfoodSession(
        session({
          topic:
            "docs 오타 1건 수정 plan action을 만들어 dry-run → 승인 → merge까지 진행해 주세요.",
        }),
      ),
    ).toBe(true);
  });

  it("matches recurring trading-mission-장전 prep sessions", () => {
    expect(
      isDogfoodSession(
        session({
          id: "2026-07-19-trading-mission-장전-2026-07-20-컨텍스트-읽기-전용-수정-금지-f",
        }),
      ),
    ).toBe(true);
  });

  it("falls back to Hangul-absence for unrecognised script/fixture slugs", () => {
    // Every script-driven dogfood/test-fixture session in this repo is an
    // ASCII kebab-case slug (dw-c2-001-inbox, f3-browser-qa, latency-probe-curl,
    // …); every organic session is a Korean sentence. No-Hangul is a stronger,
    // lower-maintenance signal than enumerating every script's naming scheme —
    // it also classifies future fixture scripts without a code change here.
    // Trade-off: a genuine English-only organic topic would also match this
    // fallback; none exist in this repo's session history today.
    expect(
      isDogfoodSession(session({ id: "dw-c2-014-execute-resolve", topic: "" })),
    ).toBe(true);
    expect(isDogfoodSession(session({ id: "f3-browser-qa", topic: "" }))).toBe(
      true,
    );
    expect(
      isDogfoodSession(session({ id: "latency-probe-curl", topic: "" })),
    ).toBe(true);
  });

  it("does not match an empty session", () => {
    expect(isDogfoodSession(session({ id: "", topic: "" }))).toBe(false);
  });
});
