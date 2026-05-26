import { useState } from "react";
import { getTheme, toggleTheme, type Theme } from "../theme";

function SunIcon() {
  return (
    <svg viewBox="0 0 16 16" fill="currentColor" aria-hidden>
      <path d="M8 1.25a.75.75 0 0 1 .75.75v1.5a.75.75 0 0 1-1.5 0V2a.75.75 0 0 1 .75-.75zm0 10.5a2.25 2.25 0 1 0 0-4.5 2.25 2.25 0 0 0 0 4.5zm-5.25-2.25a.75.75 0 0 1-.75.75H2a.75.75 0 0 1 0-1.5h1.5a.75.75 0 0 1 .75.75zm10.5 0a.75.75 0 0 1 .75-.75h1.5a.75.75 0 0 1 0 1.5h-1.5a.75.75 0 0 1-.75-.75zM4.22 4.22a.75.75 0 0 1 1.06 0l1.06 1.06a.75.75 0 1 1-1.06 1.06L4.22 5.28a.75.75 0 0 1 0-1.06zm7.5 7.5a.75.75 0 0 1 1.06 0l1.06 1.06a.75.75 0 1 1-1.06 1.06l-1.06-1.06a.75.75 0 0 1 0-1.06zm0-7.5a.75.75 0 0 1 0 1.06L10.66 6.28a.75.75 0 1 1-1.06-1.06l1.06-1.06a.75.75 0 0 1 1.06 0zM5.28 10.66a.75.75 0 0 1 0 1.06L4.22 12.78a.75.75 0 1 1-1.06-1.06l1.06-1.06a.75.75 0 0 1 1.06 0zM8 12.25a.75.75 0 0 1 .75.75v1.5a.75.75 0 0 1-1.5 0v-1.5a.75.75 0 0 1 .75-.75z" />
    </svg>
  );
}

function MoonIcon() {
  return (
    <svg viewBox="0 0 16 16" fill="currentColor" aria-hidden>
      <path d="M9.598 1.591a.75.75 0 0 1 .785-.175 5.25 5.25 0 1 0 4.8 8.784.75.75 0 0 1-.461-.698 6.751 6.751 0 0 1-5.124-7.91z" />
    </svg>
  );
}

export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(getTheme);

  function onToggle() {
    setTheme(toggleTheme());
  }

  return (
    <button
      type="button"
      className="theme-toggle"
      onClick={onToggle}
      title={theme === "light" ? "다크 모드로 전환" : "라이트 모드로 전환"}
      aria-label="테마 전환"
    >
      {theme === "light" ? <MoonIcon /> : <SunIcon />}
    </button>
  );
}
