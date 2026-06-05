const OPEN_KEY = "agent-lab-inspector-open";
const WIDTH_KEY = "agent-lab-inspector-width";

export const INSPECTOR_DEFAULT_WIDTH = 280;
export const INSPECTOR_MIN_WIDTH = 220;
export const INSPECTOR_MAX_WIDTH = 520;

export function clampInspectorWidth(width: number): number {
  return Math.min(INSPECTOR_MAX_WIDTH, Math.max(INSPECTOR_MIN_WIDTH, width));
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
