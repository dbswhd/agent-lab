import { useEffect, useRef, useState } from "react";
import type {
  AutonomyLevel,
  AutonomySessionView,
} from "../utils/autonomyLadder";
import {
  autonomyLevelCards,
  autonomyLevelLabel,
} from "../utils/autonomyLadder";
import { useLocale } from "../i18n/useLocale";

type Props = {
  readonly view: AutonomySessionView | null;
  readonly loading?: boolean;
  readonly changing?: boolean;
  readonly disabled?: boolean;
  readonly onLevelChange?: (level: AutonomyLevel) => void | Promise<void>;
};

/**
 * N4 v2: session header autonomy dial + Human level picker.
 *
 * The pill answers "do you need me right now?" rather than showing the raw
 * ceiling; ledger detail (ceiling vs display level, trust budget) moves into an
 * `advanced` disclosure so the common case stays one glance.
 */
export function AutonomyDial({
  view,
  loading,
  changing = false,
  disabled = false,
  onLevelChange,
}: Props) {
  const { locale } = useLocale();
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const cards = autonomyLevelCards(locale);
  const ko = locale === "ko";

  useEffect(() => {
    if (!open) return;
    const onDoc = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);

  if (!view && !loading) return null;

  const level = view?.displayLevel ?? "L0";
  const needsYou = view?.needsYou ?? level === "L0";
  const statusLabel = view?.statusLabel ?? (ko ? "승인 필요" : "Needs your OK");
  const title = view?.summary ?? (loading ? "…" : statusLabel);
  const interactive = Boolean(onLevelChange) && !disabled;

  return (
    <div className="autonomy-dial" ref={rootRef}>
      <button
        type="button"
        className={[
          "workspace-chrome__pill",
          "workspace-chrome__pill--autonomy",
          needsYou
            ? "workspace-chrome__pill--autonomy-needs"
            : "workspace-chrome__pill--autonomy-alone",
          `workspace-chrome__pill--${level.toLowerCase()}`,
          interactive ? "autonomy-dial__trigger" : "",
        ]
          .filter(Boolean)
          .join(" ")}
        title={title}
        aria-haspopup={interactive ? "menu" : undefined}
        aria-expanded={interactive ? open : undefined}
        aria-label={title}
        disabled={disabled || changing || loading}
        onClick={() => {
          if (!interactive) return;
          setOpen((value) => !value);
        }}
      >
        <span className="autonomy-dial__status">{statusLabel}</span>
      </button>
      {open && view ? (
        <div className="autonomy-dial__popover" role="menu">
          <p className="autonomy-dial__popover-title">
            {ko ? "언제 알아서 진행할까요?" : "When can it continue alone?"}
          </p>
          {view.whyStopped ? (
            <p className="autonomy-dial__why" role="status">
              <span className="autonomy-dial__why-label">
                {ko ? "왜 멈췄나" : "Why it paused"}
              </span>
              {view.whyStopped}
            </p>
          ) : (
            <p className="autonomy-dial__detail">{view.statusDetail}</p>
          )}
          <div className="autonomy-dial__levels">
            {cards.map((card) => {
              const active =
                card.level === view.level || card.level === view.displayLevel;
              return (
                <button
                  key={card.level}
                  type="button"
                  role="menuitemradio"
                  aria-checked={view.level === card.level}
                  className={[
                    "autonomy-dial__level-btn",
                    active ? "autonomy-dial__level-btn--active" : "",
                  ]
                    .filter(Boolean)
                    .join(" ")}
                  disabled={changing}
                  onClick={() => {
                    void onLevelChange?.(card.level);
                    setOpen(false);
                  }}
                >
                  <span className="autonomy-dial__level-btn-label">
                    {card.title}
                  </span>
                  <span className="autonomy-dial__level-btn-hint">
                    {card.hint}
                  </span>
                </button>
              );
            })}
          </div>
          <details className="autonomy-dial__advanced">
            <summary>{ko ? "세부 (개발자)" : "Details (advanced)"}</summary>
            <p className="autonomy-dial__advanced-body">
              {ko ? "상한" : "Ceiling"} {view.level} · {ko ? "표시" : "display"}{" "}
              {view.displayLevel} (
              {autonomyLevelLabel(view.displayLevel, locale)})
              {view.trustBudgetTotal > 0
                ? ` · budget ${view.trustBudgetRemaining}/${view.trustBudgetTotal}`
                : ""}
            </p>
          </details>
        </div>
      ) : null}
    </div>
  );
}
