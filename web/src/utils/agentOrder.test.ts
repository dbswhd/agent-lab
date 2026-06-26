import { describe, expect, it } from "vitest";
import {
  sortAgentIds,
  sortAgentPickerOptions,
} from "./agentOrder";

describe("agentOrder", () => {
  it("sorts agent ids in roster order", () => {
    expect(sortAgentIds(["local", "cursor", "kimi_work", "codex"])).toEqual([
      "cursor",
      "codex",
      "kimi_work",
      "local",
    ]);
  });

  it("sorts picker options by value", () => {
    const sorted = sortAgentPickerOptions([
      { value: "local", label: "Local" },
      { value: "cursor", label: "Cursor" },
      { value: "claude", label: "Claude" },
    ]);
    expect(sorted.map((row) => row.value)).toEqual([
      "cursor",
      "claude",
      "local",
    ]);
  });
});
