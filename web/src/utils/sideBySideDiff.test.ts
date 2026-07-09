import { describe, expect, it } from "vitest";
import { parseSideBySideDiff, wordDiffSegments } from "./sideBySideDiff";

describe("wordDiffSegments", () => {
  it("highlights only the token that changed, reconstructing the original text exactly", () => {
    const left = "  background: linear-gradient(180deg, #ffdedf 0%, #fb4fbc 100%);";
    const right = "  background: var(--agent-critic);";
    const { leftSegments, rightSegments } = wordDiffSegments(left, right);
    expect(leftSegments.map((s) => s.text).join("")).toBe(left);
    expect(rightSegments.map((s) => s.text).join("")).toBe(right);
    expect(leftSegments.some((s) => s.changed)).toBe(true);
    expect(rightSegments.some((s) => s.changed)).toBe(true);
    // the shared "  background" prefix must stay unchanged on both sides
    expect(leftSegments[0].changed).toBe(false);
    expect(leftSegments[0].text.startsWith("  background")).toBe(true);
    expect(rightSegments[0].changed).toBe(false);
    expect(rightSegments[0].text.startsWith("  background")).toBe(true);
  });

  it("marks identical strings as fully unchanged", () => {
    const { leftSegments, rightSegments } = wordDiffSegments("foo bar", "foo bar");
    expect(leftSegments.every((s) => !s.changed)).toBe(true);
    expect(rightSegments.every((s) => !s.changed)).toBe(true);
  });

  it("marks fully replaced tokens as changed on both sides", () => {
    const { leftSegments, rightSegments } = wordDiffSegments("aaa", "zzz");
    expect(leftSegments).toEqual([{ text: "aaa", changed: true }]);
    expect(rightSegments).toEqual([{ text: "zzz", changed: true }]);
  });

  it("falls back to whole-line-changed for pathologically long inputs", () => {
    const left = "word ".repeat(200);
    const right = "diff ".repeat(200);
    const { leftSegments, rightSegments } = wordDiffSegments(left, right);
    expect(leftSegments).toEqual([{ text: left, changed: true }]);
    expect(rightSegments).toEqual([{ text: right, changed: true }]);
  });
});

describe("parseSideBySideDiff pair rows", () => {
  it("attaches word segments to aligned del/add pairs", () => {
    const diff = [
      "@@ -1,4 +1,4 @@",
      " .avatar--orb.avatar--critic {",
      "-  background: linear-gradient(180deg, #ffdedf 0%, #fb4fbc 100%);",
      "+  background: var(--agent-critic);",
      " }",
    ].join("\n");
    const { rows } = parseSideBySideDiff(diff);
    const pairRow = rows.find((row) => row.kind === "pair");
    expect(pairRow).toBeDefined();
    expect(pairRow?.leftSegments).toBeDefined();
    expect(pairRow?.rightSegments).toBeDefined();
    const changedRightText = pairRow?.rightSegments
      ?.filter((s) => s.changed)
      .map((s) => s.text)
      .join("");
    expect(changedRightText).toContain("agent");
    expect(changedRightText).toContain("critic");
  });

  it("does not attach segments to pure add/del/ctx rows", () => {
    const diff = ["+only added", "-only removed", " context"].join("\n");
    const { rows } = parseSideBySideDiff(diff);
    for (const row of rows) {
      expect(row.leftSegments).toBeUndefined();
      expect(row.rightSegments).toBeUndefined();
    }
  });
});
