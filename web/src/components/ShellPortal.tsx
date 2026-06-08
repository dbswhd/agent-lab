import { useEffect, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";

/** Render children as a direct child of `.shell` (3rd grid column for context sidebar). */
export function ShellPortal({ children }: { children: ReactNode }) {
  const [shell, setShell] = useState<Element | null>(null);

  useEffect(() => {
    setShell(document.querySelector(".shell"));
  }, []);

  if (!shell) return null;
  return createPortal(children, shell);
}
