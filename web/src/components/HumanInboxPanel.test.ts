import { describe, expect, it } from "vitest";
import type { HumanInboxItem } from "../api/client";
import { projectInboxDecisionQueue } from "./HumanInboxPanel";

const firstQuestion: HumanInboxItem = {
  id: "question-first",
  kind: "question",
  status: "pending",
  prompt: "Choose the bounded approach",
};

const queuedQuestion: HumanInboxItem = {
  id: "question-queued",
  kind: "question",
  status: "pending",
  prompt: "Confirm the follow-up",
};

describe("projectInboxDecisionQueue", () => {
  it("keeps only the canonical first pending item active and queues the rest", () => {
    const projection = projectInboxDecisionQueue([
      firstQuestion,
      queuedQuestion,
    ]);

    expect(projection.active?.id).toBe("question-first");
    expect(projection.queuedCount).toBe(1);
  });
});
