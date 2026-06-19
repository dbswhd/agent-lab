export type WorkspaceTab =
  | "transcript"
  | "plan"
  | "background"
  | "diff"
  | "files"
  | "preview"
  | "terminal";

export type ToolPanelTab = Exclude<WorkspaceTab, "transcript">;

export type RightPanelMode = "overview" | "tasks" | "inbox" | ToolPanelTab;

/** @deprecated Use `plan` */
export type LegacyWorkspaceTab = "work" | "run" | "artifacts" | "review";

// ── P0: Overview / Tasks / Inbox / Tools  (was Tasks / Activity / Quick) ──
export type InspectorTab = "overview" | "tasks" | "inbox" | "tools";

export const WORKSPACE_TABS: {
  id: WorkspaceTab;
  label: string;
  shortcut: string;
}[] = [
  { id: "transcript", label: "Transcript", shortcut: "⌘1" },
  { id: "plan", label: "Work", shortcut: "⌘2" },
  { id: "background", label: "Background", shortcut: "⌘3" },
  { id: "diff", label: "Diff", shortcut: "⌘4" },
  { id: "files", label: "Files", shortcut: "⌘5" },
  { id: "preview", label: "Preview", shortcut: "⌘6" },
  { id: "terminal", label: "Terminal", shortcut: "⌘7" },
];

export const INSPECTOR_TABS: {
  id: InspectorTab;
  label: string;
}[] = [
  { id: "overview", label: "Overview" },
  { id: "tasks", label: "Tasks" },
  { id: "inbox", label: "Inbox" },
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
  if (tab === "work" || tab === "review" || tab === "artifacts") return "plan";
  if (tab === "run") return "background";
  return tab;
}

export function resolveDefaultWorkspaceTab(ctx: TabAutoContext): WorkspaceTab {
  if (ctx.hasDryRunDiff) return "diff";
  if (ctx.hasPendingExecution || ctx.planMd.trim()) return "plan";
  return "transcript";
}

export function resolveDefaultInspectorTab(ctx: TabAutoContext): InspectorTab {
  if (ctx.hasBlocker) return "tasks";
  return "overview"; // default → Overview
}

export function workspaceTabFromLegacy(tab: "chat" | "plan"): WorkspaceTab {
  return tab === "plan" ? "plan" : "transcript";
}
