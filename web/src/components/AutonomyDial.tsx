import { useEffect, useRef, useState } from "react";
import type {
  AutonomyLevel,
  AutonomySessionView,
} from "../utils/autonomyLadder";
import { AUTONOMY_LEVELS, autonomyLevelLabel } from "../utils/autonomyLadder";
import { useLocale } from "../i18n/useLocale";

type Props = {
  readonly view: AutonomySessionView | null;
  readonly loading?: boolean;
  readonly changing?: boolean;
  readonly disabled?: boolean;
  readonly onLevelChange?: (level: AutonomyLevel) => void | Promise<void>;
};

function transitionLabel(
  row: AutonomySessionView["transitions"][number],
  locale: "en" | "ko",
): string {
  const from = row.from ?? "?";
  const to = row.to ?? "?";
  const trigger = row.trigger ?? "auto";
  const ko = locale === "ko";
  const triggerLabel =
    trigger === "demotion"
      ? ko
        ? "강등"
        : "demotion"
      : trigger === "human"
        ? ko
          ? "Human"
          : "human"
        : ko
          ? "자동"
          : "auto";
  return `${from}→${to} · ${triggerLabel}`;
}

/** N4 v2: session header autonomy dial + Human level picker. */
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
  const label = autonomyLevelLabel(level, locale);
  const title = view?.summary ?? (loading ? "…" : label);
  const interactive = Boolean(onLevelChange) && !disabled;

  return (
    <div className="autonomy-dial" ref={rootRef}>
      <button
        type="button"
        className={[
          "workspace-chrome__pill",
          "workspace-chrome__pill--autonomy",
          `workspace-chrome__pill--${level.toLowerCase()}`,
          interactive ? "autonomy-dial__trigger" : "",
        ]
          .filter(Boolean)
          .join(" ")}
        title={title}
        aria-haspopup={interactive ? "menu" : undefined}
        aria-expanded={interactive ? open : undefined}
        disabled={disabled || changing || loading}
        onClick={() => {
          if (!interactive) return;
          setOpen((value) => !value);
        }}
      >
        <span className="autonomy-dial__level">{level}</span>
        <span className="autonomy-dial__label">{label}</span>
        {view && view.trustBudgetTotal > 0 ? (
          <span className="autonomy-dial__budget">
            {view.trustBudgetRemaining}/{view.trustBudgetTotal}
          </span>
        ) : null}
      </button>
      {open && view ? (
        <div className="autonomy-dial__popover" role="menu">
          <p className="autonomy-dial__popover-title">
            {locale === "ko" ? "자율도 ceiling" : "Autonomy ceiling"}
          </p>
          <div className="autonomy-dial__levels">
            {AUTONOMY_LEVELS.map((candidate) => {
              const active =
                candidate === view.level || candidate === view.displayLevel;
              return (
                <button
                  key={candidate}
                  type="button"
                  role="menuitemradio"
                  aria-checked={view.level === candidate}
                  className={[
                    "autonomy-dial__level-btn",
                    active ? "autonomy-dial__level-btn--active" : "",
                  ]
                    .filter(Boolean)
                    .join(" ")}
                  disabled={changing}
                  onClick={() => {
                    void onLevelChange?.(candidate);
                    setOpen(false);
                  }}
                >
                  <span className="autonomy-dial__level-btn-id">
                    {candidate}
                  </span>
                  <span className="autonomy-dial__level-btn-label">
                    {autonomyLevelLabel(candidate, locale)}
                  </span>
                </button>
              );
            })}
          </div>
          {view.transitions.length > 0 ? (
            <ul className="autonomy-dial__transitions">
              {view.transitions
                .slice()
                .reverse()
                .map((row, index) => (
                  <li
                    key={`${row.at ?? index}-${row.from}-${row.to}`}
                    className={[
                      "autonomy-dial__transition",
                      row.trigger === "demotion"
                        ? "autonomy-dial__transition--demotion"
                        : "",
                    ]
                      .filter(Boolean)
                      .join(" ")}
                  >
                    {transitionLabel(row, locale)}
                  </li>
                ))}
            </ul>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
