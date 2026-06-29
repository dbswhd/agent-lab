import { describe, expect, it } from "vitest";
import { resolveVisibleRoots, toggleVisibleRoot } from "./filesRootPrefs";

describe("filesRootPrefs", () => {
  const roots = [
    {
      root_id: "session",
      label: "session",
      kind: "session" as const,
      is_primary: false,
      missing: false,
    },
    {
      root_id: "workspace-agent-lab",
      label: "agent-lab",
      kind: "workspace" as const,
      is_primary: true,
      missing: false,
    },
    {
      root_id: "workspace-quant",
      label: "quant-pipeline",
      kind: "workspace" as const,
      is_primary: false,
      missing: false,
    },
  ];

  it("returns all roots when visible list is empty", () => {
    expect(resolveVisibleRoots(roots, [])).toEqual(roots);
  });

  it("filters and preserves order", () => {
    expect(
      resolveVisibleRoots(roots, ["workspace-quant", "session"]),
    ).toEqual([roots[2], roots[0]]);
  });

  it("keeps at least one root when toggling off the last visible root", () => {
    expect(
      toggleVisibleRoot(["session"], ["session", "workspace-agent-lab"], "session"),
    ).toEqual(["session"]);
  });
});
