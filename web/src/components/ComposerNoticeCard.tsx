import type { ReactNode } from "react";

type Props = {
  readonly title: string;
  readonly description: string;
  readonly primaryLabel?: string;
  readonly onPrimary?: () => void;
  readonly secondaryLabel?: string;
  readonly onSecondary?: () => void;
  readonly onDismiss?: () => void;
  readonly dismissLabel?: string;
  readonly busy?: boolean;
  readonly variant?: "default" | "alert" | "inbox";
  readonly visual?: ReactNode;
  readonly children?: ReactNode;
};

function NoticeIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      width="14"
      height="14"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      aria-hidden
    >
      <circle cx="12" cy="12" r="9" />
      <path d="M12 8v5" />
      <circle cx="12" cy="16.5" r="0.8" fill="currentColor" stroke="none" />
    </svg>
  );
}

function CollapseIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      width="14"
      height="14"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      aria-hidden
    >
      <path d="m8 14 4-4 4 4" />
    </svg>
  );
}

export function ComposerNoticeCard({
  title,
  description,
  primaryLabel,
  onPrimary,
  secondaryLabel,
  onSecondary,
  onDismiss,
  dismissLabel = "Dismiss",
  busy = false,
  variant = "default",
  visual: _visual,
  children,
}: Props) {
  const headline = title.trim() || "Notice";

  return (
    <article
      className={[
        "composer-notice-card",
        `composer-notice-card--${variant}`,
      ].join(" ")}
      role={variant === "alert" ? "alert" : "region"}
      aria-label={headline}
    >
      <header className="composer-notice-card__head">
        <span className="composer-notice-card__badge">
          <NoticeIcon />
          Notice
        </span>
        {onDismiss ? (
          <button
            type="button"
            className="composer-notice-card__dismiss"
            onClick={onDismiss}
            aria-label={dismissLabel}
            title={dismissLabel}
          >
            <CollapseIcon />
          </button>
        ) : null}
      </header>
      <div className="composer-notice-card__body">
        <p className="composer-notice-card__description">
          <strong className="composer-notice-card__lead">{headline}</strong>
          {description.trim() ? ` ${description.trim()}` : null}
        </p>
        {children}
        {onPrimary && primaryLabel ? (
          <div className="composer-notice-card__actions">
            {onDismiss ? (
              <button
                type="button"
                className="composer-notice-card__btn composer-notice-card__btn--secondary"
                onClick={onDismiss}
                disabled={busy}
              >
                {dismissLabel}
              </button>
            ) : onSecondary && secondaryLabel ? (
              <button
                type="button"
                className="composer-notice-card__btn composer-notice-card__btn--secondary"
                onClick={onSecondary}
                disabled={busy}
              >
                {secondaryLabel}
              </button>
            ) : null}
            <button
              type="button"
              className="composer-notice-card__btn composer-notice-card__btn--primary"
              onClick={onPrimary}
              disabled={busy}
            >
              {primaryLabel}
            </button>
          </div>
        ) : onDismiss ? (
          <div className="composer-notice-card__actions">
            <button
              type="button"
              className="composer-notice-card__btn composer-notice-card__btn--secondary"
              onClick={onDismiss}
              disabled={busy}
            >
              {dismissLabel}
            </button>
          </div>
        ) : null}
      </div>
    </article>
  );
}
