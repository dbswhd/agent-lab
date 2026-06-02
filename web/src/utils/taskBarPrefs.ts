const COLLAPSED_KEY = "agent-lab-task-bar-collapsed";

export function getTaskBarCollapsed(): boolean {
  try {
    return localStorage.getItem(COLLAPSED_KEY) === "1";
  } catch {
    return false;
  }
}

export function setTaskBarCollapsed(collapsed: boolean): void {
  try {
    localStorage.setItem(COLLAPSED_KEY, collapsed ? "1" : "0");
  } catch {
    /* ignore */
  }
}
