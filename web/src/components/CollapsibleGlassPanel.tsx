import { useState, type ReactNode } from "react";

type Props = {
  title: string;
  /** Collapsed header hint (optional). */
  summary?: string | null;
  defaultOpen?: boolean;
  variant?: "default" | "warn";
  className?: string;
  children?: ReactNode;
};

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
    "lg-panel",
    `lg-panel--${variant}`,
    open ? "lg-panel--open" : "lg-panel--collapsed",
    className,
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div className={rootClass}>
      <button
        type="button"
        className="lg-panel__head"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        <span className="lg-panel__title">{title}</span>
        {!open && summary ? (
          <span className="lg-panel__summary">{summary}</span>
        ) : null}
        <span className="lg-panel__chev" aria-hidden>
          {open ? "▾" : "▸"}
        </span>
      </button>
      {open && children != null ? (
        <div className="lg-panel__body">{children}</div>
      ) : null}
    </div>
  );
}
