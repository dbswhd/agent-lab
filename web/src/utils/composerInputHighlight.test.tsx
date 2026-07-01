import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { buildComposerHighlightNodes } from "./composerInputHighlight";

function render(value: string): string {
  return renderToStaticMarkup(<>{buildComposerHighlightNodes(value)}</>);
}

describe("buildComposerHighlightNodes", () => {
  it("wraps slash command token", () => {
    expect(render("/goal-check")).toContain('class="composer-input__token"');
    expect(render("/goal-check")).toContain("/goal-check");
  });

  it("wraps @agent token", () => {
    expect(render("@claude review this")).toContain("@claude");
    expect(
      render("@claude review this").match(/composer-input__token/g)?.length,
    ).toBe(1);
  });

  it("ignores slash mid-line", () => {
    expect(render("see /foo")).not.toContain("composer-input__token");
  });
});
