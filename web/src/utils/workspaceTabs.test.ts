import { describe, expect, it } from "vitest";
import {
  INSPECTOR_TABS,
  WORKSPACE_TABS,
  ideaLaneSurface,
  isIdeaLaneSession,
  normalizeWorkspaceTab,
  resolveDefaultWorkspaceTab,
  suppressExecuteSurfaces,
  visibleWorkbenchModes,
  type RightPanelMode,
} from "./workspaceTabs";

const ALL_MODES: readonly RightPanelMode[] = [
  "preview",
  "diff",
  "terminal",
  "files",
  "background",
  "overview",
];

describe("idea lane detection", () => {
  it("reads the lane off run.json", () => {
    expect(isIdeaLaneSession({ run: { ideation: { revision: 0 } } })).toBe(
      true,
    );
    expect(isIdeaLaneSession({ run: { topic: "실행할 작업" } })).toBe(false);
  });

  it("treats anything ambiguous as an execute-lane session", () => {
    expect(isIdeaLaneSession(null)).toBe(false);
    expect(isIdeaLaneSession(undefined)).toBe(false);
    expect(isIdeaLaneSession({})).toBe(false);
    expect(isIdeaLaneSession({ run: null })).toBe(false);
    expect(isIdeaLaneSession({ run: { ideation: null } })).toBe(false);
    expect(isIdeaLaneSession({ run: { ideation: "yes" } })).toBe(false);
  });
});

describe("workbench modes", () => {
  it("leaves an execute-lane session's tools untouched", () => {
    expect(visibleWorkbenchModes({ ideaLane: false, all: ALL_MODES })).toEqual([
      ...ALL_MODES,
    ]);
  });

  it("drops the execute-lane tools on the idea lane", () => {
    expect(visibleWorkbenchModes({ ideaLane: true, all: ALL_MODES })).toEqual([
      "overview",
    ]);
  });

  it("keeps Files only when a repo is actually bound", () => {
    expect(
      visibleWorkbenchModes({
        ideaLane: true,
        hasWorkspaceBinding: true,
        all: ALL_MODES,
      }),
    ).toEqual(["files", "overview"]);
    expect(
      visibleWorkbenchModes({
        ideaLane: true,
        hasWorkspaceBinding: false,
        all: ALL_MODES,
      }),
    ).toEqual(["overview"]);
  });

  it("never returns an empty tab strip", () => {
    for (const bound of [true, false]) {
      expect(
        visibleWorkbenchModes({
          ideaLane: true,
          hasWorkspaceBinding: bound,
          all: ALL_MODES,
        }).length,
      ).toBeGreaterThan(0);
    }
  });
});

describe("execute surfaces", () => {
  it("changes nothing for an execute-lane session", () => {
    expect(suppressExecuteSurfaces({ ideaLane: false })).toEqual({
      autonomyDial: false,
      planApproval: false,
      verifiedLoopApproval: false,
      executeBar: false,
    });
  });

  it("hides approval and execute CTAs on a new idea-lane Room", () => {
    expect(suppressExecuteSurfaces({ ideaLane: true })).toEqual({
      autonomyDial: true,
      planApproval: true,
      verifiedLoopApproval: true,
      executeBar: true,
    });
  });

  it("still lets a session finish work it already has pending", () => {
    const pending = suppressExecuteSurfaces({
      ideaLane: true,
      hasPendingExecution: true,
    });
    expect(pending.planApproval).toBe(false);
    expect(pending.executeBar).toBe(false);

    const inbox = suppressExecuteSurfaces({
      ideaLane: true,
      inboxPendingCount: 2,
    });
    expect(inbox.planApproval).toBe(false);
    expect(inbox.verifiedLoopApproval).toBe(false);
  });

  it("keeps the autonomy dial hidden even then — it is not a pending decision", () => {
    expect(
      suppressExecuteSurfaces({ ideaLane: true, hasPendingExecution: true })
        .autonomyDial,
    ).toBe(true);
  });

  it("treats an empty inbox count as no pending work", () => {
    expect(
      suppressExecuteSurfaces({ ideaLane: true, inboxPendingCount: 0 })
        .planApproval,
    ).toBe(true);
  });
});

describe("ideaLaneSurface", () => {
  const idea = { run: { ideation: { revision: 1 } } };
  const legacy = { run: { topic: "실행할 작업" } };

  it("bundles the whole decision in one call", () => {
    const s = ideaLaneSurface({
      session: idea,
      hasPendingExecution: false,
      inboxPendingCount: 0,
    });
    expect(s.ideaLane).toBe(true);
    expect(s.suppress.planApproval).toBe(true);
    expect(s.workbenchModes).toEqual(["overview"]);
  });

  it("leaves an execute-lane session with everything", () => {
    const s = ideaLaneSurface({
      session: legacy,
      hasPendingExecution: false,
      inboxPendingCount: 0,
    });
    expect(s.ideaLane).toBe(false);
    expect(s.suppress.planApproval).toBe(false);
    expect(s.workbenchModes).toHaveLength(6);
  });

  it("keeps Files when the idea session has a repo bound", () => {
    const s = ideaLaneSurface({
      session: { run: { ideation: {}, workspace_binding: { path: "/repo" } } },
      hasPendingExecution: false,
      inboxPendingCount: 0,
    });
    expect(s.workbenchModes).toEqual(["files", "overview"]);
  });

  it("does not suppress decisions an idea session still has pending", () => {
    const s = ideaLaneSurface({
      session: idea,
      hasPendingExecution: true,
      inboxPendingCount: 0,
    });
    expect(s.suppress.planApproval).toBe(false);
    expect(s.suppress.executeBar).toBe(false);
  });
});

describe("existing tab behaviour", () => {
  it("keeps the legacy tab mapping", () => {
    expect(normalizeWorkspaceTab("work")).toBe("transcript");
    expect(normalizeWorkspaceTab("run")).toBe("background");
    expect(normalizeWorkspaceTab("diff")).toBe("diff");
  });

  it("still opens Diff when a dry run produced one", () => {
    const ctx = {
      running: false,
      hasPendingExecution: false,
      hasDryRunDiff: true,
      planMd: "",
      hasBlocker: false,
    };
    expect(resolveDefaultWorkspaceTab(ctx)).toBe("diff");
    expect(resolveDefaultWorkspaceTab({ ...ctx, hasDryRunDiff: false })).toBe(
      "transcript",
    );
  });

  it("keeps the documented tab strips", () => {
    expect(WORKSPACE_TABS.map((t) => t.id)).toEqual([
      "transcript",
      "diff",
      "background",
      "files",
      "preview",
      "terminal",
    ]);
    expect(INSPECTOR_TABS.map((t) => t.id)).toEqual(["overview", "tools"]);
  });
});
