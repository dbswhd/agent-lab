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
};

const LABELS_EN: Record<string, string> = {
  git_worktree: "Git / worktree",
  worktree_hooks: "Worktree hooks",
  action_verify: "action.verify",
  oracle_verdict: "Oracle",
  open_blocks: "Open BLOCK",
  room_tasks: "Room tasks",
};

/** MB-5 — Conductor-style merge Checks SSOT. */
export function MergeChecksPanel({ checks, ko = true }: Props) {
  if (!checks?.checks?.length) return null;
  const labels = ko ? LABELS_KO : LABELS_EN;

  return (
    <section
      id="work-merge-checks"
      className="merge-checks"
      data-testid="merge-checks-panel"
    >
      <div className="merge-checks__head">
        <span className="merge-checks__title">{ko ? "Checks" : "Checks"}</span>
        {checks.merge_disabled ? (
          <span className="merge-checks__blocked" role="status">
            {ko ? "merge 비활성" : "merge disabled"}
          </span>
        ) : (
          <span className="merge-checks__ok">
            {ko ? "merge 가능" : "merge ready"}
          </span>
        )}
      </div>
      <ul className="merge-checks__list">
        {checks.checks.map((row) => (
          <li
            key={row.id}
            className={[
              "merge-checks__item",
              row.ok ? "merge-checks__item--ok" : "merge-checks__item--fail",
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
      {checks.merge_disabled_reason ? (
        <p className="merge-checks__reason">{checks.merge_disabled_reason}</p>
      ) : null}
    </section>
  );
}
