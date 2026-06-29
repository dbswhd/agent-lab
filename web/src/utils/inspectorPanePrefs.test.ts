import { describe, expect, it } from "vitest";
import {
  WORKBENCH_CANVAS_CHROME_PX,
  WORKBENCH_MAIN_COLUMN_MIN,
  WORKBENCH_PANEL_MAX_WIDTH,
  WORKBENCH_PANEL_MIN_WIDTH,
  WORKBENCH_WIDTH_CONTENT_RATIO,
  maxWorkbenchPanelWidth,
  resolveDefaultWorkbenchWidth,
  workbenchContentWidth,
} from "./inspectorPanePrefs";

const layout = { shellWidth: 1800, railWidth: 272, canvasWidth: 1528 };

describe("resolveDefaultWorkbenchWidth", () => {
  it("uses content-area ratios (shell minus rail)", () => {
    const content = workbenchContentWidth(layout);
    expect(resolveDefaultWorkbenchWidth("preview", layout)).toBe(
      Math.round(content * WORKBENCH_WIDTH_CONTENT_RATIO.preview),
    );
    expect(resolveDefaultWorkbenchWidth("terminal", layout)).toBe(
      Math.round(content * WORKBENCH_WIDTH_CONTENT_RATIO.terminal),
    );
  });

  it("keeps wide/narrow separation between modes", () => {
    const wide = resolveDefaultWorkbenchWidth("preview", layout);
    const narrow = resolveDefaultWorkbenchWidth("terminal", layout);
    expect(wide).toBeGreaterThan(narrow);
    expect(resolveDefaultWorkbenchWidth("diff", layout)).toBe(wide);
  });
});

describe("maxWorkbenchPanelWidth", () => {
  it("allows growth until main column hits its minimum", () => {
    expect(maxWorkbenchPanelWidth(layout)).toBe(
      Math.min(
        WORKBENCH_PANEL_MAX_WIDTH,
        layout.canvasWidth -
          WORKBENCH_MAIN_COLUMN_MIN -
          WORKBENCH_CANVAS_CHROME_PX,
      ),
    );
  });

  it("never goes below workbench minimum width", () => {
    expect(
      maxWorkbenchPanelWidth({
        shellWidth: 500,
        railWidth: 272,
        canvasWidth: 228,
      }),
    ).toBe(WORKBENCH_PANEL_MIN_WIDTH);
  });
});
