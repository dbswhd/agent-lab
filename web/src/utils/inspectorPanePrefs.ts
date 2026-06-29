const OPEN_KEY = "agent-lab-inspector-open";
const WIDTH_KEY = "agent-lab-inspector-width";
const TOOLS_WIDTH_KEY = "agent-lab-tools-inspector-width";
const LAST_TOOL_KEY = "agent-lab-last-tool-panel-tab";
const FILES_SIDEBAR_WIDTH_KEY = "agent-lab-files-sidebar-width";
const LAST_RIGHT_PANEL_KEY = "agent-lab-last-right-panel-mode";

export const INSPECTOR_DEFAULT_WIDTH = 280;
export const INSPECTOR_MIN_WIDTH = 220;
export const INSPECTOR_MAX_WIDTH = 520;
export const TOOLS_INSPECTOR_DEFAULT_WIDTH = 420;
export const TOOLS_INSPECTOR_MIN_WIDTH = 320;
export const TOOLS_INSPECTOR_MAX_WIDTH = 760;
export const WORKBENCH_PANEL_DEFAULT_WIDTH = 520;
export const WORKBENCH_PANEL_MIN_WIDTH = 360;
/** Soft ceiling — effective max is shell width minus rail and main column minimum. */
export const WORKBENCH_PANEL_MAX_WIDTH = 1600;
/** Main column may shrink below --composer-max-cap when workbench grows. */
export const WORKBENCH_MAIN_COLUMN_MIN = 320;
/** Gap + right inset for the floating workbench island in canvas. */
export const WORKBENCH_ISLAND_GAP = 10;
export const WORKBENCH_ISLAND_INSET = 10;
export const WORKBENCH_CANVAS_CHROME_PX =
  WORKBENCH_ISLAND_GAP + WORKBENCH_ISLAND_INSET;

/** Workbench share of the main content column (shell width minus session rail). */
export const WORKBENCH_WIDTH_CONTENT_RATIO: Record<
  StoredRightPanelMode,
  number
> = {
  overview: 0.39,
  diff: 0.70,
  files: 0.70,
  preview: 0.70,
  terminal: 0.39,
  background: 0.39,
};

/** @deprecated Use WORKBENCH_WIDTH_CONTENT_RATIO */
export const WORKBENCH_WIDTH_VIEWPORT_RATIO = WORKBENCH_WIDTH_CONTENT_RATIO;

export const WORKBENCH_WIDTH_FALLBACK: Record<StoredRightPanelMode, number> = {
  overview: 520,
  diff: 760,
  files: 640,
  preview: 780,
  terminal: 420,
  background: 440,
};
export const FILES_SIDEBAR_DEFAULT_WIDTH = 240;
export const FILES_SIDEBAR_MIN_WIDTH = 160;
export const FILES_SIDEBAR_MAX_WIDTH = 480;

const TOOL_PANEL_TABS = [
  "background",
  "diff",
  "files",
  "preview",
  "terminal",
] as const;

export type StoredToolPanelTab = (typeof TOOL_PANEL_TABS)[number];
export type StoredRightPanelMode = "overview" | StoredToolPanelTab;

const RIGHT_PANEL_MODES = [
  "overview",
  ...TOOL_PANEL_TABS,
] as const satisfies readonly StoredRightPanelMode[];

function isStoredToolPanelTab(tab: string | null): tab is StoredToolPanelTab {
  return TOOL_PANEL_TABS.some((candidate) => candidate === tab);
}

function isStoredRightPanelMode(
  tab: string | null,
): tab is StoredRightPanelMode {
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

export function clampWorkbenchPanelWidth(
  width: number,
  maxWidth = maxWorkbenchPanelWidth(),
): number {
  return Math.min(
    maxWidth,
    Math.max(WORKBENCH_PANEL_MIN_WIDTH, Math.round(width)),
  );
}

export type ShellLayoutMetrics = {
  shellWidth: number;
  railWidth: number;
  canvasWidth: number;
};

export function measureShellLayout(): ShellLayoutMetrics {
  if (typeof document === "undefined") {
    return { shellWidth: 1280, railWidth: 240, canvasWidth: 1040 };
  }
  const shell = document.querySelector(".shell");
  if (!shell) {
    return {
      shellWidth: window.innerWidth,
      railWidth: 0,
      canvasWidth: window.innerWidth,
    };
  }
  const shellWidth = shell.getBoundingClientRect().width;
  const rail = shell.querySelector(".rail");
  const railWidth = rail?.getBoundingClientRect().width ?? 0;
  const canvas = shell.querySelector(".workspace-canvas");
  const canvasWidth =
    canvas?.getBoundingClientRect().width ??
    Math.max(0, shellWidth - railWidth);
  return { shellWidth, railWidth, canvasWidth };
}

export function maxWorkbenchPanelWidth(
  layout: ShellLayoutMetrics = measureShellLayout(),
): number {
  const bySpace =
    layout.canvasWidth -
    WORKBENCH_MAIN_COLUMN_MIN -
    WORKBENCH_CANVAS_CHROME_PX;
  return Math.max(
    WORKBENCH_PANEL_MIN_WIDTH,
    Math.min(WORKBENCH_PANEL_MAX_WIDTH, Math.floor(bySpace)),
  );
}

export function clampFilesSidebarWidth(width: number): number {
  return Math.min(
    FILES_SIDEBAR_MAX_WIDTH,
    Math.max(FILES_SIDEBAR_MIN_WIDTH, width),
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
  localStorage.setItem(
    TOOLS_WIDTH_KEY,
    String(clampToolsInspectorWidth(width)),
  );
}

export function workbenchContentWidth(
  layout: ShellLayoutMetrics = measureShellLayout(),
): number {
  return Math.max(0, layout.canvasWidth);
}

export function resolveDefaultWorkbenchWidth(
  mode: StoredRightPanelMode,
  layout: ShellLayoutMetrics = measureShellLayout(),
): number {
  const contentWidth = workbenchContentWidth(layout);
  const ratio = WORKBENCH_WIDTH_CONTENT_RATIO[mode];
  const desired =
    Number.isFinite(ratio) && ratio > 0
      ? Math.round(contentWidth * ratio)
      : (WORKBENCH_WIDTH_FALLBACK[mode] ?? WORKBENCH_PANEL_DEFAULT_WIDTH);
  return clampWorkbenchPanelWidth(desired, maxWorkbenchPanelWidth(layout));
}

/** Mode default width; workbench keeps Claude ratios — main column shrinks instead. */
export function getWorkbenchPanelWidth(mode: StoredRightPanelMode): number {
  return resolveDefaultWorkbenchWidth(mode);
}

/** @deprecated Workbench width is not persisted — no-op. */
export function setWorkbenchPanelWidth(
  _mode: StoredRightPanelMode,
  _width: number,
): void {
  /* Claude-style: reopen always uses mode defaults. Main column flexes via --composer-max. */
}

export function getFilesSidebarWidth(): number {
  const stored = localStorage.getItem(FILES_SIDEBAR_WIDTH_KEY);
  const parsed = stored ? Number.parseInt(stored, 10) : Number.NaN;
  if (!Number.isFinite(parsed)) return FILES_SIDEBAR_DEFAULT_WIDTH;
  return clampFilesSidebarWidth(parsed);
}

export function setFilesSidebarWidth(width: number): void {
  localStorage.setItem(
    FILES_SIDEBAR_WIDTH_KEY,
    String(clampFilesSidebarWidth(width)),
  );
}

export function getLastToolPanelTab(): StoredToolPanelTab {
  const stored = localStorage.getItem(LAST_TOOL_KEY);
  return isStoredToolPanelTab(stored) ? stored : "diff";
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
