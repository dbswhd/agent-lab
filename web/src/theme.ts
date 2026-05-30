import { isTauri as tauriRuntime } from "@tauri-apps/api/core";

export type Theme = "light" | "dark";

const STORAGE_KEY = "agent-lab-theme";

export function getTheme(): Theme {
  const stored = localStorage.getItem(STORAGE_KEY);
  if (stored === "light" || stored === "dark") return stored;
  return "light";
}

export function applyTheme(theme: Theme): void {
  document.documentElement.setAttribute("data-theme", theme);
  localStorage.setItem(STORAGE_KEY, theme);
}

export function initTheme(): void {
  applyTheme(getTheme());
}

export function toggleTheme(): Theme {
  const next = getTheme() === "light" ? "dark" : "light";
  applyTheme(next);
  return next;
}

export function isTauriApp(): boolean {
  return tauriRuntime();
}

export function isTauri(): boolean {
  return tauriRuntime();
}
