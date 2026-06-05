export type WorkspaceTab =
  | "transcript"
  | "plan"
  | "review"
  | "run"
  | "artifacts";

export type InspectorTab = "context" | "tasks" | "run" | "settings";

export const WORKSPACE_TABS: {
  id: WorkspaceTab;
  label: string;
  shortcut: string;
}[] = [
  { id: "transcript", label: "Transcript", shortcut: "⌘1" },
  { id: "plan", label: "Plan", shortcut: "⌘2" },
  { id: "review", label: "Review", shortcut: "⌘3" },
  { id: "run", label: "Run", shortcut: "⌘4" },
  { id: "artifacts", label: "Artifacts", shortcut: "⌘5" },
];

export const INSPECTOR_TABS: {
  id: InspectorTab;
  label: string;
}[] = [
  { id: "context", label: "Context" },
  { id: "tasks", label: "Tasks" },
  { id: "run", label: "Run" },
  { id: "settings", label: "Settings" },
];

export type TabAutoContext = {
  running: boolean;
  hasPendingExecution: boolean;
  hasDryRunDiff: boolean;
  planMd: string;
  hasBlocker: boolean;
};

export function resolveDefaultWorkspaceTab(ctx: TabAutoContext): WorkspaceTab {
  if (ctx.running) return "run";
  if (ctx.hasPendingExecution || ctx.hasDryRunDiff) return "review";
  if (ctx.planMd.trim()) return "plan";
  return "transcript";
}

export function resolveDefaultInspectorTab(ctx: TabAutoContext): InspectorTab {
  if (ctx.hasBlocker) return "tasks";
  if (ctx.running) return "run";
  return "context";
}

export function workspaceTabFromLegacy(tab: "chat" | "plan"): WorkspaceTab {
  return tab === "plan" ? "plan" : "transcript";
}
