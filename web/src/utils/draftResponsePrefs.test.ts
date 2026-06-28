import { describe, expect, it } from "vitest";
import {
  getDraftOpenPref,
  latestDraftMessageIdsByAgent,
  setDraftOpenPref,
} from "./draftResponsePrefs";

describe("draftResponsePrefs", () => {
  it("tracks latest draft per agent role", () => {
    const messages = [
      { id: "c1", role: "codex", body: "first" },
      { id: "k1", role: "kimi_work", body: "kw" },
      { id: "c2", role: "codex", body: "second" },
    ];
    const open = latestDraftMessageIdsByAgent(
      messages,
      (role) => role === "codex" || role === "kimi_work",
      (body) => Boolean(body?.trim()),
    );
    expect(open.has("c1")).toBe(false);
    expect(open.has("c2")).toBe(true);
    expect(open.has("k1")).toBe(true);
  });

  it("remembers user draft toggle", () => {
    setDraftOpenPref("m1", true);
    expect(getDraftOpenPref("m1")).toBe(true);
  });
});
