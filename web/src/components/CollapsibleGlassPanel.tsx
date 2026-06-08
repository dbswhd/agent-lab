import { useState, type ReactNode } from "react";

type Props = {
  title: string;
  /** Collapsed-state summary hint (shown next to ▸ when closed). */
  summary?: string | null;
  defaultOpen?: boolean;
  /** "default" for neutral glass, "warn" for amber tint. */
  variant?: "default" | "warn";
  className?: string;
  children?: ReactNode;
};

/** CollapsibleGlassPanel — frosted collapsible panel used for
 *  plan-stale notices, dry-run summaries, etc.
 *
 *  Uses .glass-panel / .glass-panel--{variant} / .glass-panel--{open|collapsed}
 *  classes (overlays.css).
 *  Drop-in for old component that used .lg-panel (macos26.css).
 */
export function CollapsibleGlassPanel({
  title,
  summary,
  defaultOpen = true,
  variant = "default",
  className,
  children,
}: Props) {
  const [open, setOpen] = useState(defaultOpen);

  const rootClass = [
    "glass-panel",
    `glass-panel--${variant}`,
    open ? "glass-panel--open" : "glass-panel--collapsed",
    className,
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div className={rootClass}>
      <button
        type="button"
        className="glass-panel__head"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        <span className="glass-panel__title">{title}</span>
        {!open && summary ? (
          <span className="glass-panel__summary">{summary}</span>
        ) : null}
        <span className="glass-panel__chev" aria-hidden="true">
          {open ? "▾" : "▸"}
        </span>
      </button>
      {open && children != null ? (
        <div className="glass-panel__body">{children}</div>
      ) : null}
    </div>
  );
}
