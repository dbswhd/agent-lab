import type { ReactNode } from "react";

type Tone = "neutral" | "accent" | "warn" | "danger" | "ghost";

type Props = {
  readonly tone?: Tone;
  readonly badge?: ReactNode;
  readonly title?: ReactNode;
  readonly description?: ReactNode;
  readonly items?: readonly ReactNode[];
  readonly actions?: ReactNode;
  readonly compact?: boolean;
  readonly role?: "status" | "alert" | "region";
  readonly ariaLabel?: string;
  readonly children?: ReactNode;
};

/** ComposerStrip — shared "above composer" notice shell.
 *
 *  Same shape language as .exec-queue-bar / .consensus-gate-bar (badge +
 *  text stack + actions, centered at --composer-max width) so every notice
 *  directly above the composer reads as one family instead of five.
 */
export function ComposerStrip({
  tone = "neutral",
  badge,
  title,
  description,
  items,
  actions,
  compact = false,
  role = "status",
  ariaLabel,
  children,
}: Props) {
  return (
    <div
      className={[
        "composer-strip",
        `composer-strip--${tone}`,
        compact ? "composer-strip--compact" : undefined,
      ]
        .filter(Boolean)
        .join(" ")}
      role={role}
      aria-label={ariaLabel}
    >
      <div className="composer-strip__main">
        {badge ? <span className="composer-strip__badge">{badge}</span> : null}
        <div className="composer-strip__text">
          {title ? <strong className="composer-strip__title">{title}</strong> : null}
          {description ? (
            <span className="composer-strip__desc">{description}</span>
          ) : null}
          {items && items.length > 0 ? (
            <ul className="composer-strip__list">
              {items.map((item, index) => (
                // eslint-disable-next-line react/no-array-index-key
                <li key={index}>{item}</li>
              ))}
            </ul>
          ) : null}
          {children}
        </div>
      </div>
      {actions ? <div className="composer-strip__actions">{actions}</div> : null}
    </div>
  );
}
