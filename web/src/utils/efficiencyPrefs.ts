const STORAGE_KEY = "agent-lab-efficiency-mode";

export function getEfficiencyMode(): boolean {
  return localStorage.getItem(STORAGE_KEY) === "1";
}

export function setEfficiencyMode(on: boolean): void {
  localStorage.setItem(STORAGE_KEY, on ? "1" : "0");
}
