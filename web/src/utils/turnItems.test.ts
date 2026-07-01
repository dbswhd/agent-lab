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
    const thinking = items.filter((item) => item.kind === "reasoning_summary");
    expect(thinking).toHaveLength(1);
    expect(thinking[0]).toMatchObject({ text: "alpha beta", status: "running" });
  });

  it("dedupes repeated tool_start for the same command", () => {
    let items = reduceTurnItems([], {
      type: "tool_start",
      tool: "bash",
      args: { target: "git status" },
    });
    items = reduceTurnItems(items, {
      type: "tool_start",
      tool: "bash",
      args: { target: "git status" },
    });
    expect(items.filter((item) => item.kind === "tool")).toHaveLength(1);
  });

  it("upserts Codex heartbeat activity instead of stacking duplicates", () => {
    let items = reduceTurnItems([], {
      type: "agent_activity",
      text: "Codex CLI 실행 중…",
    });
    items = reduceTurnItems(items, {
      type: "agent_activity",
      text: "Codex 대기 중… (0s, events=0)",
    });
    items = reduceTurnItems(items, {
      type: "agent_activity",
      text: "Codex 대기 중… (15s, events=0)",
    });
    const activities = items.filter((item) => item.kind === "activity");
    expect(activities).toHaveLength(2);
    expect(activities[1]).toMatchObject({
      text: "Codex 대기 중… (15s, events=0)",
      status: "running",
    });
  });

  it("upserts Claude heartbeat activity instead of stacking duplicates", () => {
    let items = reduceTurnItems([], {
      type: "agent_activity",
      text: "[claude · working…]",
    });
    items = reduceTurnItems(items, {
      type: "agent_activity",
      text: "[claude · working…]",
    });
    const activities = items.filter((item) => item.kind === "activity");
    expect(activities).toHaveLength(1);
  });

  it("upserts Kimi Work net activity instead of stacking duplicates", () => {
    let items = reduceTurnItems([], {
      type: "agent_activity",
      text: "[net] Kimi Work daimon/conversations.send",
    });
    items = reduceTurnItems(items, {
      type: "agent_activity",
      text: "[net] Kimi Work daimon/conversations.send (retry)",
    });
    const activities = items.filter((item) => item.kind === "activity");
    expect(activities).toHaveLength(1);
    expect(activities[0]?.text).toContain("daimon/conversations.send");
  });
});
