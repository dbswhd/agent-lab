import { useEffect, useState } from "react";

export function useTauriFullscreen(inTauri: boolean): boolean {
  const [fullscreen, setFullscreen] = useState(false);

  useEffect(() => {
    if (!inTauri) {
      setFullscreen(false);
      return;
    }

    let cancelled = false;
    let unlistenResize: (() => void) | null = null;
    let unlistenFocus: (() => void) | null = null;

    const refresh = async () => {
      try {
        const { getCurrentWindow } = await import("@tauri-apps/api/window");
        const current = await getCurrentWindow().isFullscreen();
        if (!cancelled) setFullscreen(current);
      } catch (error) {
        if (!(error instanceof Error)) return;
        if (!cancelled) setFullscreen(false);
      }
    };

    void (async () => {
      const { getCurrentWindow } = await import("@tauri-apps/api/window");
      const currentWindow = getCurrentWindow();
      await refresh();
      unlistenResize = await currentWindow.onResized(() => {
        void refresh();
      });
      unlistenFocus = await currentWindow.onFocusChanged(() => {
        void refresh();
      });
    })().catch((error: unknown) => {
      if (!(error instanceof Error)) return;
      if (!cancelled) setFullscreen(false);
    });

    return () => {
      cancelled = true;
      unlistenResize?.();
      unlistenFocus?.();
    };
  }, [inTauri]);

  return fullscreen;
}
