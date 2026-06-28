import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { MessageMarkdown } from "./messageMarkdown";

describe("MessageMarkdown tables", () => {
  it("renders pipe tables as HTML tables", () => {
    const html = renderToStaticMarkup(
      MessageMarkdown({
        text: [
          "| line | old | new |",
          "|------|-----|-----|",
          "| 36 | room.py | room/__init__.py |",
          "| 104 | room.py, room_parallel_rounds.py | room/__init__.py, room/parallel_rounds.py |",
        ].join("\n"),
        variant: "transcript",
      }),
    );
    expect(html).toContain("<table");
    expect(html).toContain("<th");
    expect(html).toContain("room/__init__.py");
    expect(html).not.toContain("|------|");
  });
});
