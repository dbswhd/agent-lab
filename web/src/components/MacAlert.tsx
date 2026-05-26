import { useEffect, type ReactNode } from "react";

export type AlertButton = {
  label: string;
  variant?: "default" | "cancel" | "destructive";
  onClick: () => void;
};

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

  return (
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
              className={`mac-alert-btn mac-alert-btn--${b.variant ?? "default"}`}
              onClick={b.onClick}
            >
              {b.label}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
