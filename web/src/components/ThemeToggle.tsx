import { useState } from "react";
import { getTheme, toggleTheme, type Theme } from "../theme";

/**
 * Rebuilt theme toggle. Behavior preserved (getTheme/toggleTheme from theme.ts).
 * New 24px stroke icons matching the design system icon set.
 */
function SunIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      width="17"
      height="17"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.7}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
    </svg>
  );
}
function MoonIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      width="17"
      height="17"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.7}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />
    </svg>
  );
}

export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(getTheme);
  return (
    <button
      type="button"
      className="icon-btn"
      onClick={() => setTheme(toggleTheme())}
      title={theme === "light" ? "다크 모드로 전환" : "라이트 모드로 전환"}
      aria-label="테마 전환"
    >
      {theme === "light" ? <MoonIcon /> : <SunIcon />}
    </button>
  );
}
