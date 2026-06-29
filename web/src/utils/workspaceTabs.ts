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
