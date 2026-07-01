import { useEffect, useId, useState } from "react";
import type {
  PlanTodoProgress,
  PlanTodoRow,
  PlanDiffRollup,
} from "../utils/planTodoView";
import { WorkPlanIcon } from "./WorkPlanIcon";

type Props = {
  rows: PlanTodoRow[];
  progress: PlanTodoProgress;
  diffRollup: PlanDiffRollup;
  locale: "en" | "ko";
  variant?: "tool" | "composer";
  loading?: boolean;
  busy?: boolean;
  selectedKey: string | null;
  disabled?: boolean;
  planFileLabel?: string;
  onSelect: (key: string) => void;
  onRefClick?: (line: number) => void;
  onPlanFileClick?: () => void;
  defaultExpanded?: boolean;
  children?: React.ReactNode;
};

export function PlanTodoList({
  rows,
  progress,
  diffRollup,
  locale,
  variant = "tool",
  loading = false,
  busy = false,
  selectedKey,
  disabled = false,
  planFileLabel = "plan.md",
  onSelect,
  onRefClick: _onRefClick,
  onPlanFileClick,
  defaultExpanded = true,
  children,
}: Props) {
  const ko = locale === "ko";
  const panelId = useId();
  const [expanded, setExpanded] = useState(defaultExpanded);

  useEffect(() => {
    if (busy) setExpanded(false);
  }, [busy]);

  const isComposer = variant === "composer";

  return (
    <section
      className={[
        "plan-card plan-todo-surface composer-dock-card",
        variant === "composer"
          ? "plan-todo-surface--composer composer-dock-card--composer"
          : "",
        expanded
          ? "plan-todo-surface--expanded"
          : "plan-todo-surface--collapsed",
      ]
        .filter(Boolean)
        .join(" ")}
      id="work-plan-review"
      aria-label={ko ? "실행 계획" : "Execution plan"}
    >
      <div className="plan-todo-surface__head">
        <button
          type="button"
          className="plan-todo-surface__toggle"
          aria-expanded={expanded}
          aria-controls={panelId}
          onClick={() => setExpanded((open) => !open)}
        >
          <span className="plan-todo-surface__head-main">
            <span className="plan-todo-surface__eyebrow composer-dock-card__eyebrow">
              <WorkPlanIcon name="list" size={14} />
              <span className="plan-todo-surface__title composer-dock-card__title">
                {ko ? "할 일" : "To-dos"}
              </span>
              {rows.length > 0 ? (
                <span className="plan-todo-surface__count composer-dock-card__count">
                  {rows.length}
                </span>
              ) : null}
            </span>
            {!expanded ? (
              <span className="plan-todo-surface__summary composer-dock-card__summary">
                {busy ? (
                  <span className="plan-todo-surface__spinner" aria-hidden />
                ) : null}
                <span className="plan-todo-surface__summary-text">
                  {progress.total > 0
                    ? ko
                      ? `${progress.current}/${progress.total}단계`
                      : `Step ${progress.current}/${progress.total}`
                    : ko
                      ? "0단계"
                      : "Step 0"}
                  {diffRollup.fileCount > 0 ? (
                    <>
                      {" · "}
                      {ko
                        ? `${diffRollup.fileCount}개 파일 변경됨`
                        : `${diffRollup.fileCount} file${diffRollup.fileCount === 1 ? "" : "s"} changed`}{" "}
                      <span className="plan-todo-surface__add">
                        +{diffRollup.adds}
                      </span>{" "}
                      <span className="plan-todo-surface__del">
                        -{diffRollup.dels}
                      </span>
                    </>
                  ) : null}
                </span>
              </span>
            ) : null}
          </span>
          <span
            className={[
              "plan-todo-surface__chevron",
              expanded ? "plan-todo-surface__chevron--open" : "",
            ]
              .filter(Boolean)
              .join(" ")}
            aria-hidden
          />
        </button>
        {expanded ? (
          onPlanFileClick ? (
            <button
              type="button"
              className="plan-todo-surface__plan-link"
              onClick={onPlanFileClick}
            >
              {planFileLabel}
            </button>
          ) : (
            <span className="plan-todo-surface__plan-label">
              {planFileLabel}
            </span>
          )
        ) : null}
      </div>

      {expanded ? (
        <div
          id={panelId}
          className="plan-todo-surface__body composer-dock-card__body"
        >
          {loading ? (
            <p className="plan-card__muted">
              {ko ? "액션 불러오는 중…" : "Loading actions…"}
            </p>
          ) : rows.length === 0 ? null : (
            <ul className="plan-todo-list" role="list">
              {rows.map((row) => {
                const itemBody = (
                  <>
                    <span
                      className={[
                        "plan-todo-item__check",
                        row.status === "done"
                          ? "plan-todo-item__check--done"
                          : "",
                        row.status === "active"
                          ? "plan-todo-item__check--active"
                          : "",
                        row.status === "gate"
                          ? "plan-todo-item__check--gate"
                          : "",
                      ]
                        .filter(Boolean)
                        .join(" ")}
                      aria-hidden
                    />
                    <span className="plan-todo-item__content">
                      <span className="plan-todo-item__label">{row.label}</span>
                      {row.where || row.verify ? (
                        <span className="plan-todo-item__meta">
                          {row.where ? (
                            <span className="plan-todo-item__where">
                              {row.where}
                            </span>
                          ) : null}
                          {row.verify ? (
                            <span className="plan-todo-item__verify">
                              {row.verify}
                            </span>
                          ) : null}
                        </span>
                      ) : null}
                    </span>
                  </>
                );

                if (isComposer || !row.selectable) {
                  return (
                    <li
                      key={row.key}
                      className={[
                        "plan-todo-item",
                        !row.selectable ? "plan-todo-item--gate" : "",
                        row.status === "done" ? "plan-todo-item--done" : "",
                        row.status === "active" ? "plan-todo-item--active" : "",
                      ]
                        .filter(Boolean)
                        .join(" ")}
                    >
                      {itemBody}
                    </li>
                  );
                }

                const selected = selectedKey === row.key;

                return (
                  <li key={row.key} className="plan-todo-item">
                    <button
                      type="button"
                      className={[
                        "plan-todo-item__button",
                        selected ? "plan-todo-item__button--selected" : "",
                        row.status === "done"
                          ? "plan-todo-item__button--done"
                          : "",
                        row.status === "active"
                          ? "plan-todo-item__button--active"
                          : "",
                        disabled ? "plan-todo-item__button--disabled" : "",
                      ]
                        .filter(Boolean)
                        .join(" ")}
                      disabled={disabled}
                      aria-pressed={selected}
                      onClick={() => onSelect(row.key)}
                    >
                      {itemBody}
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
          {children}
        </div>
      ) : null}
    </section>
  );
}
