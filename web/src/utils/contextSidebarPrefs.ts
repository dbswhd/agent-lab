const STORAGE_KEY = "agent-lab-context-sidebar-open";

export function getContextSidebarOpen(): boolean {
  const stored = localStorage.getItem(STORAGE_KEY);
  if (stored === "1" || stored === "true") return true;
  return false;
}

export function setContextSidebarOpen(open: boolean): void {
  localStorage.setItem(STORAGE_KEY, open ? "1" : "0");
}
