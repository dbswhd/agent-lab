import type { ReactNode } from "react";

type Props = {
  readonly title: string;
  readonly description: string;
  readonly primaryLabel: string;
  readonly onPrimary: () => void;
  readonly secondaryLabel?: string;
  readonly onSecondary?: () => void;
  readonly onDismiss?: () => void;
  readonly dismissLabel?: string;
  readonly busy?: boolean;
  readonly variant?: "default" | "alert" | "inbox";
  readonly visual?: ReactNode;
  readonly children?: ReactNode;
};

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
  visual,
  children,
}: Props) {
  return (
    <article
      className={[
        "composer-notice-card",
        `composer-notice-card--${variant}`,
      ].join(" ")}
      role={variant === "alert" ? "alert" : "region"}
      aria-label={title}
    >
      {visual ? (
        <div className="composer-notice-card__visual">{visual}</div>
      ) : null}
      <div className="composer-notice-card__body">
        <div className="composer-notice-card__copy">
          <h3 className="composer-notice-card__title">{title}</h3>
          <p className="composer-notice-card__description">{description}</p>
        </div>
        {children}
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
      </div>
    </article>
  );
}
