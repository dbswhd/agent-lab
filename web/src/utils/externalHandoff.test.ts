import { describe, expect, it } from "vitest";
import {
  buildDelegatePrompt,
  externalHandoffBadgeLabel,
  externalHandoffChecksSummary,
} from "./externalHandoff";

describe("externalHandoffBadgeLabel", () => {
  it("labels codex delegate handoffs", () => {
    expect(
      externalHandoffBadgeLabel({
        stopped_cleanly: true,
        changed_files: [],
        checks: [],
        evidence_summary: "done",
        risks: [],
        tool_id: "external:codex-delegate",
      }),
    ).toBe("Codex delegate");
  });

  it("labels legacy GJC handoffs", () => {
    expect(
      externalHandoffBadgeLabel({
        stopped_cleanly: true,
        changed_files: [],
        checks: [],
        evidence_summary: "done",
        risks: [],
        source: "gjc",
      }),
    ).toBe("GJC handoff");
  });
});

describe("externalHandoffChecksSummary", () => {
  it("summarizes passing checks", () => {
    expect(
      externalHandoffChecksSummary({
        stopped_cleanly: true,
        changed_files: [],
        checks: [
          { cmd: "make test", exit: 0 },
          { cmd: "lint", exit: 1 },
        ],
        evidence_summary: "x",
        risks: [],
      }),
    ).toBe("Checks 1/2");
  });
});

describe("buildDelegatePrompt", () => {
  it("includes plan action fields and handoff contract", () => {
    const prompt = buildDelegatePrompt({
      what: "add README line",
      where: "README.md",
      verify: "make test-fast",
    });
    expect(prompt).toContain("add README line");
    expect(prompt).toContain("README.md");
    expect(prompt).toContain("stopped_cleanly");
  });
});
