import { describe, expect, it } from "vitest";
import { effectiveTurnAgents, parseAgentMentions } from "./agentMentions";

describe("agentMentions", () => {
  it("parses @codex from composer text", () => {
    expect(parseAgentMentions("@codex 마저 해봐", ["codex", "claude"])).toEqual(
      ["codex"],
    );
  });

  it("limits pending roster to mentioned agents", () => {
    expect(
      effectiveTurnAgents("@codex 마저 해봐", ["codex", "claude", "kimi_work"]),
    ).toEqual(["codex"]);
  });
});
