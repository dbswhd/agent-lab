import { useState } from "react";
import { getTheme, toggleTheme, type Theme } from "../theme";

const RAYS = [0, 45, 90, 135, 180, 225, 270, 315] as const;

/** Geometric sun — circle + rays centered at (8, 8). */
function SunIcon() {
  return (
    <svg
      viewBox="0 0 16 16"
      width="16"
      height="16"
      aria-hidden
      className="theme-icon theme-icon--sun"
    >
      <circle cx="8" cy="8" r="2.25" fill="currentColor" />
      <g stroke="currentColor" strokeWidth="1.25" strokeLinecap="round" fill="none">
        {RAYS.map((deg) => {
          const rad = (deg * Math.PI) / 180;
          const inner = 4.6;
          const outer = 6.4;
          return (
            <line
              key={deg}
              x1={8 + Math.cos(rad) * inner}
              y1={8 + Math.sin(rad) * inner}
              x2={8 + Math.cos(rad) * outer}
              y2={8 + Math.sin(rad) * outer}
            />
          );
        })}
      </g>
    </svg>
  );
}

/** Crescent moon centered in 16×16. */
function MoonIcon() {
  return (
    <svg
      viewBox="0 0 16 16"
      width="16"
      height="16"
      aria-hidden
      className="theme-icon theme-icon--moon"
    >
      <path
        fill="currentColor"
        d="M8.2 2.4a5.6 5.6 0 1 0 5.1 8.35A4.2 4.2 0 1 1 8.2 2.4Z"
      />
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
