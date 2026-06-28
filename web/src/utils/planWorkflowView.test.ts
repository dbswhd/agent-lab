import { describe, expect, it } from "vitest";
import {
  hasPlanWorkflowClarifySurface,
  isComposerPlanWorkflowNotice,
  pendingClarifierQuestionCount,
  shouldShowPlanWorkflowComposerNotice,
} from "./planWorkflowView";

describe("planWorkflowView clarify surfaces", () => {
  it("counts unanswered clarifier prompts", () => {
    expect(
      pendingClarifierQuestionCount({
        questions: [
          { prompt: "Scope?", answered: false },
          { prompt: "Done", answered: true },
        ],
      }),
    ).toBe(1);
  });

  it("hides idle CLARIFY composer notice when nothing is pending", () => {
    expect(
      shouldShowPlanWorkflowComposerNotice({
        showBanner: true,
        showHint: false,
        phase: "CLARIFY",
        inboxPendingCount: 0,
        notice: undefined,
        clarifierInterview: { questions: [] },
      }),
    ).toBe(false);
  });

  it("shows CLARIFY surface when inbox or open questions exist", () => {
    expect(
      hasPlanWorkflowClarifySurface({
        phase: "CLARIFY",
        inboxPendingCount: 2,
        clarifierInterview: null,
      }),
    ).toBe(true);
    expect(
      hasPlanWorkflowClarifySurface({
        phase: "INTAKE",
        inboxPendingCount: 0,
        clarifierInterview: {
          questions: [{ prompt: "Goal?", answered: false }],
        },
      }),
    ).toBe(true);
  });

  it("ignores internal clarity_pending notice when inbox is empty", () => {
    expect(isComposerPlanWorkflowNotice("clarity_pending")).toBe(false);
    expect(
      shouldShowPlanWorkflowComposerNotice({
        showBanner: true,
        showHint: false,
        phase: "CLARIFY",
        inboxPendingCount: 0,
        notice: "clarity_pending",
        clarifierInterview: { questions: [] },
      }),
    ).toBe(false);
  });
});
