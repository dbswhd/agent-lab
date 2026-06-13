export type WorkspaceTab =
  | "transcript"
  | "work"
  | "run"
  | "artifacts"
  | "files";

/** @deprecated Use `work` */
export type LegacyWorkspaceTab = "plan" | "review";

// ── P0: Overview / Tasks / Inbox  (was Tasks / Activity / Quick) ──
export type InspectorTab = "overview" | "tasks" | "inbox";

export const WORKSPACE_TABS: {
  id: WorkspaceTab;
  label: string;
  shortcut: string;
}[] = [
  { id: "transcript", label: "Transcript", shortcut: "⌘1" },
  { id: "work",       label: "Work",       shortcut: "⌘2" },
  { id: "run",        label: "Run",         shortcut: "⌘3" },
  { id: "artifacts",  label: "Artifacts",  shortcut: "⌘4" },
  { id: "files",      label: "Files",      shortcut: "⌘5" },
];

export const INSPECTOR_TABS: {
  id: InspectorTab;
  label: string;
}[] = [
  { id: "overview", label: "Overview" },
  { id: "tasks",    label: "Tasks"    },
  { id: "inbox",    label: "Inbox"    },
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
  if (tab === "plan" || tab === "review") return "work";
  return tab;
}

export function resolveDefaultWorkspaceTab(ctx: TabAutoContext): WorkspaceTab {
  if (ctx.hasPendingExecution || ctx.hasDryRunDiff) return "work";
  if (ctx.planMd.trim()) return "work";
  return "transcript";
}

export function resolveDefaultInspectorTab(ctx: TabAutoContext): InspectorTab {
  if (ctx.hasBlocker) return "tasks";
  return "overview";                          // default → Overview
}

export function workspaceTabFromLegacy(tab: "chat" | "plan"): WorkspaceTab {
  return tab === "plan" ? "work" : "transcript";
}
