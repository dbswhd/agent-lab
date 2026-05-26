const STORAGE_KEY = "agent-lab-sidebar-open";

export function getSidebarOpen(): boolean {
  const stored = localStorage.getItem(STORAGE_KEY);
  if (stored === "0" || stored === "false") return false;
  return true;
}

export function setSidebarOpen(open: boolean): void {
  localStorage.setItem(STORAGE_KEY, open ? "1" : "0");
}
