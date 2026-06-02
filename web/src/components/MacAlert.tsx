import { useEffect, type ReactNode } from "react";
import { createPortal } from "react-dom";

export type AlertButton = {
  label: string;
  variant?: "default" | "cancel" | "destructive";
  onClick: () => void;
};

function alertButtonClass(variant: AlertButton["variant"] = "default"): string {
  const classes = ["mac-alert-btn"];
  if (variant === "destructive") {
    classes.push("mac-alert-btn--destructive");
  } else if (variant === "cancel") {
    classes.push("mac-alert-btn--cancel");
  } else {
    classes.push("mac-alert-btn--default");
  }
  return classes.join(" ");
}

type Props = {
  open: boolean;
  title: string;
  message?: string;
  children?: ReactNode;
  buttons: AlertButton[];
  onClose?: () => void;
};

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
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && onClose) onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  return createPortal(
    <div
      className="mac-alert-backdrop"
      role="presentation"
      onClick={(e) => {
        if (e.target === e.currentTarget && onClose) onClose();
      }}
    >
      <div
        className={`mac-alert${children ? " mac-alert--form" : ""}`}
        role="alertdialog"
        aria-labelledby="mac-alert-title"
        aria-modal="true"
      >
        <div className="mac-alert-body">
          <h2 id="mac-alert-title" className="mac-alert-title">
            {title}
          </h2>
          {message && <p className="mac-alert-message">{message}</p>}
          {children}
        </div>
        <div className="mac-alert-actions">
          {buttons.map((b) => (
            <button
              key={b.label}
              type="button"
              className={alertButtonClass(b.variant)}
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
