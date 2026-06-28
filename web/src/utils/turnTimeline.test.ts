import { describe, expect, it } from "vitest";
import {
  formatTurnActivitySummary,
  formatWorkedDuration,
  summarizeTurnItems,
  turnItemsDurationSeconds,
} from "./turnTimeline";
import type { TurnItem } from "./turnItems";

describe("turnTimeline", () => {
  it("formats worked duration", () => {
    expect(formatWorkedDuration(0)).toBe("Worked for 0s");
    expect(formatWorkedDuration(45)).toBe("Worked for 45s");
    expect(formatWorkedDuration(125)).toBe("Worked for 2m 5s");
  });

  it("derives elapsed seconds from tool timestamps", () => {
    const items: TurnItem[] = [
      {
        id: "t1",
        kind: "tool",
        tool: "shell",
        startedAt: 1_000,
        doneAt: 4_500,
      },
    ];
    expect(turnItemsDurationSeconds(items, 9_000)).toBe(4);
  });

  it("summarizes turn activity like Cursor", () => {
    const items: TurnItem[] = [
      {
        id: "e1",
        kind: "tool",
        tool: "write",
        args: "src/a.py",
        startedAt: 1,
        doneAt: 2,
        output: "+3\n-1",
      },
      {
        id: "r1",
        kind: "tool",
        tool: "read_file",
        args: "src/b.py",
        startedAt: 3,
        doneAt: 4,
      },
      {
        id: "s1",
        kind: "tool",
        tool: "grep",
        args: "pattern",
        startedAt: 5,
        doneAt: 6,
      },
      {
        id: "c1",
        kind: "tool",
        tool: "shell",
        args: "pytest",
        startedAt: 7,
        doneAt: 8,
      },
    ];
    const stats = summarizeTurnItems(items);
    expect(formatTurnActivitySummary(stats)).toBe(
      "Edited 1 file, explored 1 file, 1 search, ran 1 command",
    );
    expect(stats.linesAdded).toBe(1);
    expect(stats.linesRemoved).toBe(1);
  });
});
