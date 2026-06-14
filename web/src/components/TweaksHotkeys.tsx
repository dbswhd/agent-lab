import { useEffect } from "react";
import { useTweaksDemo } from "../context/TweaksDemoContext";

/** Global ⌘⇧T shortcut to toggle the Tweaks panel. */
export function TweaksHotkeys() {
  const { togglePanel } = useTweaksDemo();

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (!e.metaKey || !e.shiftKey || e.altKey) return;
      if (e.key.toLowerCase() !== "t") return;
      e.preventDefault();
      togglePanel();
    }
    window.addEventListener("keydown", onKey, { capture: true });
    return () =>
      window.removeEventListener("keydown", onKey, { capture: true });
  }, [togglePanel]);

  return null;
}
