import { describe, expect, it } from "vitest";
import { ConceptPanel } from "./ConceptPanel";
import {
  actionRequestId,
  buildCandidateRows,
  buildCombineCommand,
  buildRejectCommand,
  buildResetCommand,
  buildSelectCommand,
  combinedOptionId,
  combinedSelectionRow,
  keyboardIntent,
  rejectedOptionIds,
  selectedOptionId,
  shouldReloadAfter,
  stageView,
  statusAfterReload,
  statusFromError,
  type IdeationState,
} from "../utils/conceptPanelView";

// This repo has no DOM test environment (no jsdom / Testing Library), and all
// existing suites are plain vitest over pure modules. The panel keeps its
// decidable behaviour in `conceptPanelView` for exactly that reason, so these
// tests cover what the panel decides rather than how React paints it.

function state(patch: Partial<IdeationState> = {}): IdeationState {
  return {
    schema_version: 1,
    revision: 2,
    stage: "explore",
    options: [
      {
        id: "opt-0-cursor",
        title: "A안",
        agent: "cursor",
        principle: "원리 A",
      },
      {
        id: "opt-0-codex",
        title: "B안",
        agent: "codex",
        principle: "원리 B",
        usage: "장면 B",
        difference: "차이 B",
        tradeoff: "포기 B",
        first_experiment: "실험 B",
      },
      {
        id: "opt-0-claude",
        agent: "claude",
        raw: "형식이 깨진 원문",
        parse_error: "no_recognized_sections",
      },
    ],
    selection: null,
    decisions: [],
    ...patch,
  };
}

describe("ConceptPanel module", () => {
  it("exports a component", () => {
    expect(typeof ConceptPanel).toBe("function");
  });
});

describe("candidate rows", () => {
  it("keeps stored order and drops empty sections", () => {
    const rows = buildCandidateRows(state());
    expect(rows.map((r) => r.id)).toEqual([
      "opt-0-cursor",
      "opt-0-codex",
      "opt-0-claude",
    ]);
    expect(rows[0].fields.map((f) => f.label)).toEqual(["작동 원리"]);
    expect(rows[1].fields.map((f) => f.label)).toEqual([
      "작동 원리",
      "사용 장면",
      "다른 점",
      "포기하는 것",
      "첫 실험",
    ]);
  });

  it("shows an unparsed candidate instead of hiding it", () => {
    const rows = buildCandidateRows(state());
    expect(rows[2].unparsedText).toBe("형식이 깨진 원문");
    expect(rows[2].title).toBe("opt-0-claude");
    expect(rows[0].unparsedText).toBeNull();
  });

  it("restores selection and rejection from stored state", () => {
    const rows = buildCandidateRows(
      state({
        selection: { option_id: "opt-0-codex", source_revision: 2 },
        decisions: [
          { kind: "select", option_id: "opt-0-codex" },
          { kind: "reject", option_id: "opt-0-cursor", reason: "안 맞음" },
        ],
      }),
    );
    expect(rows.find((r) => r.id === "opt-0-codex")?.selected).toBe(true);
    expect(rows.find((r) => r.id === "opt-0-cursor")?.rejected).toBe(true);
    expect(rows.find((r) => r.id === "opt-0-claude")?.rejected).toBe(false);
  });

  it("reads selection and rejections off the record", () => {
    const s = state({
      selection: { option_id: "opt-0-codex" },
      decisions: [
        { kind: "reject", option_id: "opt-0-cursor" },
        { kind: "reject", option_id: "opt-0-cursor" },
        { kind: "reopen" },
      ],
    });
    expect(selectedOptionId(s)).toBe("opt-0-codex");
    expect(rejectedOptionIds(s)).toEqual(["opt-0-cursor"]);
    expect(selectedOptionId(null)).toBeNull();
    expect(buildCandidateRows(null)).toEqual([]);
  });

  it("surfaces a combined selection that has no option row", () => {
    const combined = combinedSelectionRow(
      state({
        selection: {
          option_id: "opt-combined-opt-0-cursor-opt-0-codex",
          parent_ids: ["opt-0-cursor", "opt-0-codex"],
          reason: "둘을 합침",
        },
      }),
    );
    expect(combined?.parents).toEqual(["opt-0-cursor", "opt-0-codex"]);
    expect(combined?.reason).toBe("둘을 합침");
    expect(combinedSelectionRow(state())).toBeNull();
    expect(
      combinedSelectionRow(state({ selection: { option_id: "opt-0-codex" } })),
    ).toBeNull();
  });
});

describe("stage labels", () => {
  it("uses the §4.2 vocabulary, never APPROVED/VERIFIED", () => {
    expect(stageView(state())?.label).toBe("구상 비교 중");
    expect(stageView(state({ stage: "shape" }))?.label).toBe("구상 선택");
    expect(stageView(state({ stage: "plan" }))?.label).toBe("계획 준비됨");
    for (const stage of ["explore", "shape", "plan"] as const) {
      const view = stageView(state({ stage }));
      expect(view?.label).not.toMatch(/APPROVED|VERIFIED/i);
      expect(view?.hint).toBeTruthy();
    }
    expect(stageView(null)).toBeNull();
  });
});

describe("failure surfaces", () => {
  it("distinguishes stale from busy from a generic failure", () => {
    expect(
      statusFromError({
        status: 409,
        code: "stale_revision",
        currentRevision: 5,
        message: "stale",
      }),
    ).toEqual({
      kind: "stale",
      currentRevision: 5,
      message: expect.stringContaining("바뀌었습니다"),
    });
    expect(
      statusFromError({ status: 409, code: "busy", message: "busy" }).kind,
    ).toBe("busy");
    expect(statusFromError({ status: 500, message: "서버 오류" })).toEqual({
      kind: "error",
      message: "서버 오류",
    });
  });

  it("treats a missing ideation state as absent, not as an error", () => {
    expect(statusFromError({ status: 404, message: "no ideation" }).kind).toBe(
      "absent",
    );
  });

  it("reloads only after a stale response", () => {
    expect(
      shouldReloadAfter({ kind: "stale", currentRevision: 3, message: "x" }),
    ).toBe(true);
    expect(shouldReloadAfter({ kind: "busy", message: "x" })).toBe(false);
    expect(shouldReloadAfter({ kind: "error", message: "x" })).toBe(false);
    expect(shouldReloadAfter({ kind: "idle" })).toBe(false);
  });

  it("keeps the stale notice visible through the reload it triggers", () => {
    const stale = {
      kind: "stale",
      currentRevision: 5,
      message: "바뀜",
    } as const;
    expect(statusAfterReload(stale)).toEqual(stale);
    expect(statusAfterReload({ kind: "busy", message: "x" })).toEqual({
      kind: "idle",
    });
    expect(statusAfterReload()).toEqual({ kind: "idle" });
  });

  it("falls back to a message when the error is unusable", () => {
    expect(statusFromError(null).kind).toBe("error");
    const unusable = statusFromError({});
    expect(unusable.kind).toBe("error");
    expect(unusable.kind === "error" && unusable.message).toBe("요청 실패");
  });
});

describe("commands", () => {
  it("carries expected_revision so a stale write is refused server-side", () => {
    const cmd = buildSelectCommand({
      optionId: "opt-0-codex",
      revision: 2,
      requestId: "r",
    });
    expect(cmd).toEqual({
      command: "select",
      option_id: "opt-0-codex",
      reason: "",
      expected_revision: 2,
      request_id: "r",
    });
  });

  it("gives the same action the same request id so a retry is a duplicate", () => {
    const a = actionRequestId("sess", 2, "select:opt-0-codex");
    const b = actionRequestId("sess", 2, "select:opt-0-codex");
    expect(a).toBe(b);
    expect(actionRequestId("sess", 3, "select:opt-0-codex")).not.toBe(a);
  });

  it("derives a deterministic id for a combination", () => {
    const parents = ["opt-0-cursor", "opt-0-codex"];
    const first = buildCombineCommand({
      parentIds: parents,
      revision: 2,
      requestId: "r",
    });
    const again = buildCombineCommand({
      parentIds: parents,
      revision: 2,
      requestId: "r",
    });
    expect(first.new_id).toBe(again.new_id);
    expect(first.new_id).toBe(combinedOptionId(parents));
    expect(first.parent_ids).toEqual(parents);
    expect(combinedOptionId(parents).length).toBeLessThanOrEqual(64);
  });

  it("builds reject and reset", () => {
    expect(
      buildRejectCommand({
        optionId: "opt-0-cursor",
        revision: 1,
        requestId: "r",
      }).command,
    ).toBe("reject");
    const reset = buildResetCommand({ revision: 4, requestId: "r" });
    expect(reset.command).toBe("reset");
    expect(reset.expected_revision).toBe(4);
    expect(reset.option_id).toBeUndefined();
  });
});

describe("keyboard", () => {
  it("moves a roving focus without running off either end", () => {
    expect(keyboardIntent({ key: "ArrowDown", index: 0, count: 3 })).toEqual({
      kind: "move",
      index: 1,
    });
    expect(keyboardIntent({ key: "ArrowDown", index: 2, count: 3 })).toEqual({
      kind: "move",
      index: 2,
    });
    expect(keyboardIntent({ key: "ArrowUp", index: 0, count: 3 })).toEqual({
      kind: "move",
      index: 0,
    });
    expect(keyboardIntent({ key: "Home", index: 2, count: 3 })).toEqual({
      kind: "move",
      index: 0,
    });
    expect(keyboardIntent({ key: "End", index: 0, count: 3 })).toEqual({
      kind: "move",
      index: 2,
    });
  });

  it("compares and selects from the keyboard", () => {
    expect(keyboardIntent({ key: "Enter", index: 1, count: 3 }).kind).toBe(
      "select",
    );
    expect(keyboardIntent({ key: " ", index: 1, count: 3 }).kind).toBe(
      "select",
    );
    expect(keyboardIntent({ key: "c", index: 1, count: 3 }).kind).toBe(
      "toggleCompare",
    );
    expect(keyboardIntent({ key: "x", index: 1, count: 3 }).kind).toBe(
      "reject",
    );
    expect(keyboardIntent({ key: "Delete", index: 1, count: 3 }).kind).toBe(
      "reject",
    );
  });

  it("ignores keys it does not own, and an empty list", () => {
    expect(keyboardIntent({ key: "a", index: 0, count: 3 }).kind).toBe("none");
    expect(keyboardIntent({ key: "Tab", index: 0, count: 3 }).kind).toBe(
      "none",
    );
    expect(keyboardIntent({ key: "ArrowDown", index: 0, count: 0 }).kind).toBe(
      "none",
    );
  });
});
