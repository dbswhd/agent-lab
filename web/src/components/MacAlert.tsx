import { useEffect, type ReactNode } from "react";
import { createPortal } from "react-dom";

export type AlertButton = {
  label: string;
  /**
   * Button style variant:
   *   "default"     → neutral secondary button (same as omitting variant)
   *   "primary"     → filled accent button (confirm / ok)
   *   "cancel"      → muted label, no background
   *   "destructive" → danger-coloured
   *
   * "default" is kept as an alias so existing call sites don't need updating.
   */
  variant?: "default" | "primary" | "cancel" | "destructive";
  onClick: () => void;
};

function alertBtnClass(variant: AlertButton["variant"] = "default"): string {
  // "default" maps to the base .alert-btn (no modifier) — same visual as "cancel"
  // but kept as a distinct semantic for call-site clarity.
  if (variant === "default") return "alert-btn";
  return `alert-btn alert-btn--${variant}`;
}

type Props = {
  open: boolean;
  title: string;
  message?: string;
  /** Optional form content rendered between message and action buttons. */
  children?: ReactNode;
  buttons: AlertButton[];
  onClose?: () => void;
};

/** MacAlert — canonical system-level alert / confirm dialog.
 *
 *  Uses .alert-backdrop / .alert / .alert-btn-* classes (overlays.css).
 *  Drop-in for old .mac-alert-backdrop / .mac-alert (macos26.css).
 *
 *  variant "default" is kept as an alias for call-site compatibility —
 *  it renders the same neutral button as omitting the variant entirely.
 *
 *  Renders into document.body via portal.
 */
export function MacAlert({
  open,
  title,
  message,
  children,
  buttons,
  onClose,
}: Props) {
  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape" && onClose) onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  return createPortal(
    <div
      className="alert-backdrop"
      role="presentation"
      onClick={(e) => {
        if (e.target === e.currentTarget && onClose) onClose();
      }}
    >
      <div
        className={`alert${children ? " alert--form" : ""}`}
        role="alertdialog"
        aria-labelledby="mac-alert-title"
        aria-modal="true"
      >
        <div className="alert__body">
          <h2 id="mac-alert-title" className="alert__title">{title}</h2>
          {message ? <p className="alert__message">{message}</p> : null}
        </div>
        {children ? <div className="alert__form-body">{children}</div> : null}
        <div className="alert__actions">
          {buttons.map((b) => (
            <button
              key={b.label}
              type="button"
              className={alertBtnClass(b.variant)}
              onClick={b.onClick}
            >
              {b.label}
            </button>
          ))}
        </div>
      </div>
    </div>,
    document.body,
  );
}
