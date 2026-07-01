import { describe, expect, it } from "vitest";
import {
  filterAgentMentions,
  mentionQueryLooksLikePath,
} from "./composerAgentMention";

describe("filterAgentMentions", () => {
  const agents = [
    { id: "claude", label: "Claude" },
    { id: "kimi_work", label: "Kimi Work" },
  ];

  it("returns all agents for empty query", () => {
    expect(filterAgentMentions("", agents)).toHaveLength(2);
  });

  it("filters by id prefix", () => {
    expect(filterAgentMentions("clau", agents).map((a) => a.id)).toEqual([
      "claude",
    ]);
  });

  it("matches kimi_work via hyphen alias in query", () => {
    expect(filterAgentMentions("kimi-work", agents).map((a) => a.id)).toEqual([
      "kimi_work",
    ]);
  });
});

describe("mentionQueryLooksLikePath", () => {
  it("detects path-like queries", () => {
    expect(mentionQueryLooksLikePath("src/foo.py")).toBe(true);
    expect(mentionQueryLooksLikePath("claude")).toBe(false);
  });
});
