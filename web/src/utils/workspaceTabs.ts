export type WorkspaceTab =
  | "transcript"
  | "background"
  | "diff"
  | "files"
  | "preview"
  | "terminal";

export type ToolPanelTab = Exclude<WorkspaceTab, "transcript">;

export type RightPanelMode = "overview" | ToolPanelTab;

/** @deprecated Work tab removed — use composer event stack */
export type LegacyWorkspaceTab =
  | "work"
  | "run"
  | "artifacts"
  | "review"
  | "plan";

export type InspectorTab = "overview" | "tools";

export const WORKSPACE_TABS: {
  id: WorkspaceTab;
  label: string;
  shortcut: string;
}[] = [
  { id: "transcript", label: "Transcript", shortcut: "⌘1" },
  { id: "diff", label: "Diff", shortcut: "⌘2" },
  { id: "background", label: "Background", shortcut: "⌘3" },
  { id: "files", label: "Files", shortcut: "⌘4" },
  { id: "preview", label: "Preview", shortcut: "⌘5" },
  { id: "terminal", label: "Terminal", shortcut: "⌘6" },
];

export const INSPECTOR_TABS: {
  id: InspectorTab;
  label: string;
}[] = [
  { id: "overview", label: "Overview" },
  { id: "tools", label: "Tools" },
];

export type TabAutoContext = {
  running: boolean;
  hasPendingExecution: boolean;
  hasDryRunDiff: boolean;
  planMd: string;
  hasBlocker: boolean;
};

/** RI-12 — idea-lane surface.
 *
 * Read straight off the session's `run.json`: a session without `ideation` is
 * an execute-lane session and nothing below changes for it.
 */
export function isIdeaLaneSession(
  session: { run?: Record<string, unknown> | null } | null | undefined,
): boolean {
  const ideation = session?.run?.ideation;
  return Boolean(ideation && typeof ideation === "object");
}

/** Workbench modes offered for a session.
 *
 * The idea lane's work is the conversation, the candidates, and the plan —
 * Diff / Terminal / Background / Preview are execute-lane tools and would
 * imply this Room runs code. `overview` stays so the session is inspectable,
 * and `files` stays only when a repo is actually bound.
 */
export function visibleWorkbenchModes(args: {
  ideaLane: boolean;
  hasWorkspaceBinding?: boolean;
  all: readonly RightPanelMode[];
}): RightPanelMode[] {
  const { ideaLane, hasWorkspaceBinding, all } = args;
  if (!ideaLane) return [...all];
  return all.filter(
    (mode) =>
      mode === "overview" || (mode === "files" && Boolean(hasWorkspaceBinding)),
  );
}

/** Execute-lane decision surfaces the idea lane must not show.
 *
 * Suppression is per-surface and only for a *new* Room: an existing session
 * carrying a pending execution or an open Inbox item keeps every surface it
 * needs to resolve it (§RI-12).
 */
export function suppressExecuteSurfaces(args: {
  ideaLane: boolean;
  hasPendingExecution?: boolean;
  inboxPendingCount?: number;
}): {
  autonomyDial: boolean;
  planApproval: boolean;
  verifiedLoopApproval: boolean;
  executeBar: boolean;
} {
  const unresolvedLegacyWork =
    Boolean(args.hasPendingExecution) || (args.inboxPendingCount ?? 0) > 0;
  const hide = args.ideaLane && !unresolvedLegacyWork;
  return {
    autonomyDial: args.ideaLane,
    planApproval: hide,
    verifiedLoopApproval: hide,
    executeBar: hide,
  };
}

const ALL_WORKBENCH_MODES: readonly RightPanelMode[] = [
  "preview",
  "diff",
  "terminal",
  "files",
  "background",
  "overview",
];

export type IdeaLaneSurface = {
  ideaLane: boolean;
  suppress: ReturnType<typeof suppressExecuteSurfaces>;
  workbenchModes: RightPanelMode[];
};

/** One call for the whole idea-lane surface decision.
 *
 * Lives here rather than inline in `RoomChatView` so the shell stays thin —
 * that file is under the F9 LOC ratchet precisely to stop logic collecting in
 * it — and so this is testable without a DOM.
 */
export function ideaLaneSurface(args: {
  session: { run?: Record<string, unknown> | null } | null | undefined;
  hasPendingExecution: boolean;
  inboxPendingCount: number;
}): IdeaLaneSurface {
  const ideaLane = isIdeaLaneSession(args.session);
  return {
    ideaLane,
    suppress: suppressExecuteSurfaces({
      ideaLane,
      hasPendingExecution: args.hasPendingExecution,
      inboxPendingCount: args.inboxPendingCount,
    }),
    workbenchModes: visibleWorkbenchModes({
      ideaLane,
      hasWorkspaceBinding: Boolean(args.session?.run?.workspace_binding),
      all: ALL_WORKBENCH_MODES,
    }),
  };
}

export function normalizeWorkspaceTab(
  tab: WorkspaceTab | LegacyWorkspaceTab,
): WorkspaceTab {
  if (
    tab === "work" ||
    tab === "review" ||
    tab === "artifacts" ||
    tab === "plan"
  ) {
    return "transcript";
  }
  if (tab === "run") return "background";
  return tab;
}

export function resolveDefaultWorkspaceTab(ctx: TabAutoContext): WorkspaceTab {
  if (ctx.hasDryRunDiff) return "diff";
  return "transcript";
}

export function resolveDefaultInspectorTab(_ctx: TabAutoContext): InspectorTab {
  return "overview";
}

export function workspaceTabFromLegacy(tab: "chat" | "plan"): WorkspaceTab {
  return tab === "plan" ? "transcript" : "transcript";
}
