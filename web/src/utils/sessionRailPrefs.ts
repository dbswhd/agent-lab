const WIDTH_KEY = "agent-lab-session-rail-width";

export const SESSION_RAIL_DEFAULT_WIDTH = 268;
export const SESSION_RAIL_MIN_WIDTH = 200;
export const SESSION_RAIL_MAX_WIDTH = 520;

export function clampSessionRailWidth(width: number): number {
  return Math.min(
    SESSION_RAIL_MAX_WIDTH,
    Math.max(SESSION_RAIL_MIN_WIDTH, width),
  );
}

export function getSessionRailWidth(): number {
  const stored = localStorage.getItem(WIDTH_KEY);
  const parsed = stored ? Number.parseInt(stored, 10) : Number.NaN;
  if (!Number.isFinite(parsed)) return SESSION_RAIL_DEFAULT_WIDTH;
  return clampSessionRailWidth(parsed);
}

export function setSessionRailWidth(width: number): void {
  localStorage.setItem(WIDTH_KEY, String(clampSessionRailWidth(width)));
}
