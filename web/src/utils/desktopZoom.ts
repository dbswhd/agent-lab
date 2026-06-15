import { isTauri } from "../theme";

const ZOOM_KEY = "agent-lab-zoom";
const MIN_ZOOM = 0.5;
const MAX_ZOOM = 3;
const STEP = 0.1;

function clamp(value: number): number {
  return Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, Math.round(value * 100) / 100));
}

function readZoom(): number {
  const raw = Number(localStorage.getItem(ZOOM_KEY));
  return Number.isFinite(raw) && raw > 0 ? clamp(raw) : 1;
}

async function applyZoom(factor: number): Promise<void> {
  const { getCurrentWebview } = await import("@tauri-apps/api/webview");
  await getCurrentWebview().setZoom(factor);
}

/**
 * Tauri-only: restore the saved zoom factor and wire ⌘/Ctrl +/-/0 hotkeys.
 * No-op in the browser (zoom works natively there).
 */
export function initDesktopZoom(): void {
  if (!isTauri()) return;

  let zoom = readZoom();
  const commit = (next: number) => {
    zoom = clamp(next);
    localStorage.setItem(ZOOM_KEY, String(zoom));
    void applyZoom(zoom).catch(() => {});
  };

  // Restore on launch.
  void applyZoom(zoom).catch(() => {});

  window.addEventListener(
    "keydown",
    (event) => {
      if (!(event.metaKey || event.ctrlKey) || event.altKey) return;
      switch (event.key) {
        case "=":
        case "+":
          event.preventDefault();
          commit(zoom + STEP);
          break;
        case "-":
        case "_":
          event.preventDefault();
          commit(zoom - STEP);
          break;
        case "0":
          event.preventDefault();
          commit(1);
          break;
        default:
          break;
      }
    },
    { capture: true },
  );
}
