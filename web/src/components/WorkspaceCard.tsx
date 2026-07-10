import type { MergeChecksPayload, PlanExecutionRecord } from "../api/client";
import { MergeChecksPanel } from "./MergeChecksPanel";
import { PlanDiffStat } from "./PlanDiffStat";
import { ExternalHandoffBadge } from "./PlanExecutePanelSupport";
import {
  isWorktreeExecution,
  mergedCommitSha,
  worktreeBannerLines,
} from "../utils/planExecuteWorktree";

type Props = {
  execution: PlanExecutionRecord;
  mergeChecks?: MergeChecksPayload | null;
  onOpenDiff?: () => void;
  onOpenFiles?: () => void;
  onOpenFile?: (path: string) => void;
};

/**
 * Conductor-style workspace card — worktree · branch · diff · checks · archive · handoff
 * in one surface (ABSORB W1-A / NORTH-STAR §2.5).
 */
export function WorkspaceCard({
  execution,
  mergeChecks = null,
  onOpenDiff,
  onOpenFiles,
  onOpenFile,
}: Props) {
  const lines = worktreeBannerLines(execution);
  const worktree = isWorktreeExecution(execution);
  const mergeSha = mergedCommitSha(execution);
  const archivePath = `executed/${execution.id}.json`;
  const hasIdentity =
    Boolean(lines.worktree || lines.branch || lines.base || lines.commit) ||
    Boolean(execution.diff_stat?.trim()) ||
    Boolean(mergeChecks?.checks?.length) ||
    Boolean(execution.external_handoff?.evidence_summary) ||
    Boolean(mergeSha);

  if (!hasIdentity) return null;

  return (
    <section
      className="workspace-card"
      data-testid="workspace-card"
      aria-label="workspace"
    >
      <header className="workspace-card__head">
        <h3 className="workspace-card__title">Workspace</h3>
        <span className="workspace-card__mode">
          {worktree ? "Worktree" : execution.isolation_effective || "Local"}
        </span>
      </header>

      <div className="work-exec-worktree-banner" role="status">
        {lines.worktree ? (
          <p className="work-exec-worktree-banner__line">
            <span className="work-exec-worktree-banner__label">path</span>
            <code className="work-exec-worktree-banner__path">
              {lines.worktree}
            </code>
          </p>
        ) : null}
        {lines.branch ? (
          <p className="work-exec-worktree-banner__line">
            <span className="work-exec-worktree-banner__label">branch</span>
            <code>{lines.branch}</code>
          </p>
        ) : null}
        {lines.base ? (
          <p className="work-exec-worktree-banner__line">
            <span className="work-exec-worktree-banner__label">base</span>
            <code>{lines.base}</code>
          </p>
        ) : null}
        {lines.commit ? (
          <p className="work-exec-worktree-banner__line">
            <span className="work-exec-worktree-banner__label">commit</span>
            <code>{lines.commit.slice(0, 7)}</code>
          </p>
        ) : null}
      </div>

      {execution.diff_stat?.trim() ? (
        <div className="workspace-card__diff">
          <div className="workspace-card__section-label">
            <span>Diff</span>
            {onOpenDiff ? (
              <button
                type="button"
                className="btn btn--sm btn--ghost"
                onClick={onOpenDiff}
              >
                Open
              </button>
            ) : null}
          </div>
          <PlanDiffStat text={execution.diff_stat} />
        </div>
      ) : null}

      {mergeChecks?.checks?.length ? (
        <MergeChecksPanel checks={mergeChecks} />
      ) : null}

      <ExternalHandoffBadge row={execution} />

      <footer className="workspace-card__actions">
        {mergeSha || onOpenFile || onOpenFiles ? (
          <button
            type="button"
            className="btn btn--sm btn--ghost"
            onClick={() => {
              if (onOpenFile) onOpenFile(archivePath);
              else onOpenFiles?.();
            }}
            title={archivePath}
          >
            Archive
            {mergeSha ? ` · ${mergeSha.slice(0, 7)}` : ""}
          </button>
        ) : null}
        {execution.external_handoff?.evidence_summary ? (
          <span className="workspace-card__handoff-hint">
            Handoff ready — review in IDE / export
          </span>
        ) : null}
      </footer>
    </section>
  );
}
