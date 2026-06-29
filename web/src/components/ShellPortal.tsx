import { useEffect, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";

/** Render children inside `.workspace-canvas` (workbench tile beside main workspace). */
export function ShellPortal({ children }: { children: ReactNode }) {
  const [host, setHost] = useState<Element | null>(null);

  useEffect(() => {
    setHost(document.querySelector(".workspace-canvas"));
  }, []);

  if (!host) return null;
  return createPortal(children, host);
}
