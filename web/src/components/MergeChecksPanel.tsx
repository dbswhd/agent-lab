import { useId, useState } from "react";
import type { MergeChecksPayload } from "../api/client";

type Props = {
  checks: MergeChecksPayload | null | undefined;
  ko?: boolean;
};

const LABELS_KO: Record<string, string> = {
  git_worktree: "Git / worktree",
  worktree_hooks: "Worktree hooks",
  action_verify: "action.verify",
  oracle_verdict: "Oracle",
  open_blocks: "Open BLOCK",
  room_tasks: "Room tasks",
  diff_safety: "Diff 안전성",
  syntax_gate: "구문 검사",
};

const LABELS_EN: Record<string, string> = {
  git_worktree: "Git / worktree",
  worktree_hooks: "Worktree hooks",
  action_verify: "action.verify",
  oracle_verdict: "Oracle",
  open_blocks: "Open BLOCK",
  room_tasks: "Room tasks",
  diff_safety: "Diff safety",
  syntax_gate: "Syntax gate",
};

/**
 * MB-5 — Conductor-style merge Checks SSOT.
 * Collapsed by default to a one-line pass count; auto-expands when merge is
 * blocked or any check fails, so problems are never hidden behind a click.
 */
export function MergeChecksPanel({ checks, ko = true }: Props) {
  const panelId = useId();
  const rows = checks?.checks ?? [];
  const needsAttention =
    Boolean(checks?.merge_disabled) || rows.some((row) => !row.ok);
  const [expanded, setExpanded] = useState(needsAttention);

  if (!rows.length) return null;
  const passCount = rows.filter((row) => row.ok).length;
  const labels = ko ? LABELS_KO : LABELS_EN;
  const open = expanded || needsAttention;

  return (
    <section
      id="work-merge-checks"
      className={[
        "merge-checks",
        open ? "merge-checks--expanded" : "merge-checks--collapsed",
      ].join(" ")}
      data-testid="merge-checks-panel"
    >
      <button
        type="button"
        className="merge-checks__toggle"
        aria-expanded={open}
        aria-controls={panelId}
        disabled={needsAttention}
        onClick={() => setExpanded((prev) => !prev)}
      >
        <span className="merge-checks__title">Checks</span>
        <span className="merge-checks__count">
          {passCount}/{rows.length}
        </span>
        {checks?.merge_disabled ? (
          <span className="merge-checks__blocked" role="status">
            {ko ? "merge 비활성" : "merge disabled"}
          </span>
        ) : (
          <span className="merge-checks__ok">
            {ko ? "merge 가능" : "merge ready"}
          </span>
        )}
        {!needsAttention ? (
          <span
            className={[
              "merge-checks__chevron",
              open ? "merge-checks__chevron--open" : "",
            ]
              .filter(Boolean)
              .join(" ")}
            aria-hidden
          />
        ) : null}
      </button>
      {open ? (
        <div id={panelId} className="merge-checks__body">
          <ul className="merge-checks__list">
            {rows.map((row) => (
              <li
                key={row.id}
                className={[
                  "merge-checks__item",
                  row.ok
                    ? "merge-checks__item--ok"
                    : "merge-checks__item--fail",
                ].join(" ")}
              >
                <span className="merge-checks__label">
                  {labels[row.id] ?? row.id}
                </span>
                <span className="merge-checks__detail">
                  {row.detail ?? (row.ok ? "OK" : "FAIL")}
                </span>
              </li>
            ))}
          </ul>
          {checks?.merge_disabled_reason ? (
            <p className="merge-checks__reason">
              {checks.merge_disabled_reason}
            </p>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
