import { describe, expect, it } from "vitest";
import type { AgentOption } from "../api/client";
import { formatRoomModelLine } from "./roomModels";
import {
  reduceTurnItems,
  type TurnItem,
  type TurnItemEvent,
} from "./turnItems";

const events: TurnItemEvent[] = [
  { type: "agent_activity", text: "Reading repository" },
  { type: "tool_start", tool: "shell", args: { target: "npm test" } },
  { type: "tool_output", tool: "shell", chunk: "passed" },
  { type: "tool_done", tool: "shell" },
  { type: "agent_done" },
];

describe("turn item reducer", () => {
  it("produces identical live and replay state", () => {
    const live = events.reduce(
      (items, event, index) => reduceTurnItems(items, event, index + 1),
      [] as TurnItem[],
    );
    const replay = events.reduce(
      (items, event, index) => reduceTurnItems(items, event, index + 1),
      [] as TurnItem[],
    );
    expect(replay).toEqual(live);
    expect(live[0]).toMatchObject({ kind: "activity", status: "done" });
    expect(live[1]).toMatchObject({
      kind: "tool",
      tool: "shell",
      output: "passed",
      doneAt: 4,
    });
  });

  it("renders any roster size and preserves long model names", () => {
    const agents = Array.from({ length: 6 }, (_, index) => ({
      id: `agent-${index}`,
      label: `Agent ${index + 1}`,
      model: `provider/model-with-a-long-name-${index}`,
      ready: true,
    })) as AgentOption[];
    const line = formatRoomModelLine(agents);
    expect(line.split(" · ")).toHaveLength(6);
    expect(line).toContain("provider/model-with-a-long-name-5");
  });

  it("replaces in-place thinking activity lines", () => {
    let items = reduceTurnItems([], {
      type: "agent_activity",
      text: "[thinking] alpha",
    });
    items = reduceTurnItems(items, {
      type: "agent_activity",
      text: "[thinking] alpha beta",
    });
    const thinking = items.filter(
      (item) => item.kind === "activity" && item.text.startsWith("[thinking]"),
    );
    expect(thinking).toHaveLength(1);
    expect(thinking[0]?.text).toBe("[thinking] alpha beta");
  });
});
