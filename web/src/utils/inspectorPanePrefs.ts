const OPEN_KEY = "agent-lab-inspector-open";
const WIDTH_KEY = "agent-lab-inspector-width";
const TOOLS_WIDTH_KEY = "agent-lab-tools-inspector-width";
const LAST_TOOL_KEY = "agent-lab-last-tool-panel-tab";
const WORKBENCH_WIDTH_KEY = "agent-lab-workbench-panel-width";
const LAST_RIGHT_PANEL_KEY = "agent-lab-last-right-panel-mode";

export const INSPECTOR_DEFAULT_WIDTH = 280;
export const INSPECTOR_MIN_WIDTH = 220;
export const INSPECTOR_MAX_WIDTH = 520;
export const TOOLS_INSPECTOR_DEFAULT_WIDTH = 420;
export const TOOLS_INSPECTOR_MIN_WIDTH = 320;
export const TOOLS_INSPECTOR_MAX_WIDTH = 760;
export const WORKBENCH_PANEL_DEFAULT_WIDTH = 520;
export const WORKBENCH_PANEL_MIN_WIDTH = 360;
export const WORKBENCH_PANEL_MAX_WIDTH = 860;

const TOOL_PANEL_TABS = [
  "plan",
  "background",
  "diff",
  "files",
  "preview",
  "terminal",
] as const;

export type StoredToolPanelTab = (typeof TOOL_PANEL_TABS)[number];
export type StoredRightPanelMode =
  | "overview"
  | "tasks"
  | "inbox"
  | StoredToolPanelTab;

const RIGHT_PANEL_MODES = [
  "overview",
  "tasks",
  "inbox",
  ...TOOL_PANEL_TABS,
] as const satisfies readonly StoredRightPanelMode[];

function isStoredToolPanelTab(tab: string | null): tab is StoredToolPanelTab {
  return TOOL_PANEL_TABS.some((candidate) => candidate === tab);
}

function isStoredRightPanelMode(tab: string | null): tab is StoredRightPanelMode {
  return RIGHT_PANEL_MODES.some((candidate) => candidate === tab);
}

export function clampInspectorWidth(width: number): number {
  return Math.min(INSPECTOR_MAX_WIDTH, Math.max(INSPECTOR_MIN_WIDTH, width));
}

export function clampToolsInspectorWidth(width: number): number {
  return Math.min(
    TOOLS_INSPECTOR_MAX_WIDTH,
    Math.max(TOOLS_INSPECTOR_MIN_WIDTH, width),
  );
}

export function clampWorkbenchPanelWidth(width: number): number {
  return Math.min(
    WORKBENCH_PANEL_MAX_WIDTH,
    Math.max(WORKBENCH_PANEL_MIN_WIDTH, width),
  );
}

export function getInspectorOpen(): boolean {
  const stored = localStorage.getItem(OPEN_KEY);
  if (stored === "0" || stored === "false") return false;
  return true;
}

export function setInspectorOpen(open: boolean): void {
  localStorage.setItem(OPEN_KEY, open ? "1" : "0");
}

export function getInspectorWidth(): number {
  const stored = localStorage.getItem(WIDTH_KEY);
  const parsed = stored ? Number.parseInt(stored, 10) : Number.NaN;
  if (!Number.isFinite(parsed)) return INSPECTOR_DEFAULT_WIDTH;
  return clampInspectorWidth(parsed);
}

export function setInspectorWidth(width: number): void {
  localStorage.setItem(WIDTH_KEY, String(clampInspectorWidth(width)));
}

export function getToolsInspectorWidth(): number {
  const stored = localStorage.getItem(TOOLS_WIDTH_KEY);
  const parsed = stored ? Number.parseInt(stored, 10) : Number.NaN;
  if (!Number.isFinite(parsed)) return TOOLS_INSPECTOR_DEFAULT_WIDTH;
  return clampToolsInspectorWidth(parsed);
}

export function setToolsInspectorWidth(width: number): void {
  localStorage.setItem(TOOLS_WIDTH_KEY, String(clampToolsInspectorWidth(width)));
}

export function getWorkbenchPanelWidth(): number {
  const stored = localStorage.getItem(WORKBENCH_WIDTH_KEY);
  const parsed = stored ? Number.parseInt(stored, 10) : Number.NaN;
  if (!Number.isFinite(parsed)) return WORKBENCH_PANEL_DEFAULT_WIDTH;
  return clampWorkbenchPanelWidth(parsed);
}

export function setWorkbenchPanelWidth(width: number): void {
  localStorage.setItem(WORKBENCH_WIDTH_KEY, String(clampWorkbenchPanelWidth(width)));
}

export function getLastToolPanelTab(): StoredToolPanelTab {
  const stored = localStorage.getItem(LAST_TOOL_KEY);
  return isStoredToolPanelTab(stored) ? stored : "plan";
}

export function setLastToolPanelTab(tab: StoredToolPanelTab): void {
  localStorage.setItem(LAST_TOOL_KEY, tab);
}

export function getLastRightPanelMode(): StoredRightPanelMode {
  const stored = localStorage.getItem(LAST_RIGHT_PANEL_KEY);
  return isStoredRightPanelMode(stored) ? stored : "overview";
}

export function setLastRightPanelMode(mode: StoredRightPanelMode): void {
  localStorage.setItem(LAST_RIGHT_PANEL_KEY, mode);
}
