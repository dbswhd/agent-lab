import { useState } from "react";
import {
  resolveSessionObjection,
  type PlanActionItem,
  type PlanExecutionRecord,
  type RoomObjection,
  type RoomTask,
} from "../api/client";
import type { AgentPermissions } from "../utils/agentPermissions";
import { fullAgentPermissions } from "../utils/agentPermissions";
import { formatExecutionTime } from "../utils/planExecuteHistory";
import { WorkPlanIcon } from "./WorkPlanIcon";
import {
  isWorktreeExecution,
  worktreeBannerLines,
} from "../utils/planExecuteWorktree";

export function linkedTaskForAction(
  tasks: RoomTask[] | undefined,
  actionIndex: number | undefined,
): RoomTask | undefined {
  if (actionIndex == null || !tasks?.length) return undefined;
  return (
    tasks.find(
      (t) =>
        t.plan_action_index === actionIndex &&
        t.status !== "completed" &&
        t.status !== "cancelled",
    ) ?? tasks.find((t) => t.plan_action_index === actionIndex)
  );
}

export function PlanLinkedTaskLine({
  task,
  onFocusTask,
}: {
  task: RoomTask | undefined;
  onFocusTask?: (taskId: string) => void;
}) {
  if (!task || !onFocusTask) return null;
  return (
    <p className="plan-card__linked-task">
      연결 작업:{" "}
      <button
        type="button"
        className="plan-card__linked-task-btn"
        onClick={() => onFocusTask(task.id)}
        title="작업 바로 이동"
      >
        {task.title}
      </button>
    </p>
  );
}

export function formatPathList(paths: string[] | undefined, max = 3): string {
  if (!paths?.length) return "";
  if (paths.length <= max) return paths.join(", ");
  const head = paths.slice(0, max).join(", ");
  return `${head} +${paths.length - max} more`;
}

export function executePermissions(): AgentPermissions {
  return fullAgentPermissions();
}

export function reviewRequiredLabel(
  row: PlanExecutionRecord | null | undefined,
): string {
  if (!row) return "PDF 확인 후 승인";
  const artifacts = row.verification_artifacts;
  const pages =
    artifacts?.pdf_page_count ??
    (artifacts?.break_report as { baselinePdfPageCount?: number } | undefined)
      ?.baselinePdfPageCount;
  const pdfPath =
    artifacts?.pdf_path ??
    row.artifact_touched_paths?.find((p) => p.toLowerCase().endsWith(".pdf")) ??
    row.verification_paths?.find((p) => p.toLowerCase().endsWith(".pdf"));
  const pageBit = pages != null ? `${pages}p` : null;
  if (pdfPath && pageBit) {
    return `PDF 확인 후 승인 · ${pdfPath} (${pageBit})`;
  }
  if (pdfPath) {
    return `PDF 확인 후 승인 · ${pdfPath}`;
  }
  if (pageBit) {
    return `PDF 확인 후 승인 (${pageBit})`;
  }
  return "PDF 확인 후 승인";
}

export function statusLabel(
  status: string | undefined,
  row?: PlanExecutionRecord | null,
): string {
  switch (status) {
    case "pending_approval":
      return "승인 대기";
    case "completed":
      return "완료";
    case "review_required":
      return reviewRequiredLabel(row);
    case "rejected":
      return "거부됨";
    case "superseded":
      return "재작업으로 대체됨";
    case "merged":
      return "main에 병합됨";
    case "merge_conflict":
      return "merge 충돌";
    case "failed":
      return "실패";
    default:
      return status || "—";
  }
}

function oracleEvidence(row: PlanExecutionRecord) {
  return row.verify_after_merge?.oracle ?? row.oracle ?? null;
}

export function oracleStatus(row: PlanExecutionRecord): string | null {
  return row.verify_after_merge?.status ?? oracleEvidence(row)?.verdict ?? null;
}

export function oracleStatusLabel(status: string | null): string {
  switch (status) {
    case "passed":
    case "pass":
      return "Oracle PASS";
    case "failed":
    case "fail":
      return "Oracle FAIL";
    case "skipped":
      return "Oracle SKIP";
    default:
      return "Oracle —";
  }
}

export function ExternalHandoffBadge({ row }: { row: PlanExecutionRecord }) {
  const handoff = row.external_handoff;
  if (!handoff?.evidence_summary) return null;
  const clean = handoff.stopped_cleanly !== false;
  return (
    <div
      className={`work-exec-handoff work-exec-handoff--${clean ? "ok" : "warn"}`}
      role="status"
      data-testid="external-handoff-badge"
    >
      <span className="work-exec-handoff__badge">
        {clean ? "External handoff" : "External handoff (unclean stop)"}
      </span>
      <p className="work-exec-handoff__summary">{handoff.evidence_summary}</p>
      {handoff.changed_files?.length ? (
        <p className="work-exec-handoff__files">
          {handoff.changed_files.slice(0, 5).join(", ")}
          {handoff.changed_files.length > 5 ? " …" : ""}
        </p>
      ) : null}
    </div>
  );
}

export function AdversarialBadge({ row }: { row: PlanExecutionRecord }) {
  const note = row.adversarial_note?.trim();
  if (!note) return null;
  const tone = note.toUpperCase() === "LGTM" ? "lgtm" : "warning";
  return (
    <div
      className={`work-exec-adversarial work-exec-adversarial--${tone}`}
      role="status"
    >
      <span className="work-exec-adversarial__badge">
        {tone === "lgtm" ? "Adversarial LGTM" : "Adversarial review"}
      </span>
      {row.adversarial_source ? (
        <span className="work-exec-adversarial__meta">
          {row.adversarial_source}
        </span>
      ) : null}
      {tone !== "lgtm" ? (
        <span className="work-exec-adversarial__detail" title={note}>
          {note}
        </span>
      ) : null}
    </div>
  );
}

export function OracleBadge({
  row,
  busy,
  onReverify,
}: {
  row: PlanExecutionRecord;
  busy: boolean;
  onReverify: (executionId: string) => void;
}) {
  const status = oracleStatus(row);
  const oracle = oracleEvidence(row);
  if (!status && !oracle) return null;
  const failed = status === "failed" || status === "fail";
  const checked = row.verify_after_merge?.checked_at ?? oracle?.checked_at;
  const retryCount =
    row.verify_retries ?? row.verify_after_merge?.verify_retries ?? 0;
  const retryLimitReached = retryCount >= MAX_VERIFY_RETRIES;
  const detail = oracle?.detail?.trim();
  return (
    <div
      className={`work-exec-oracle work-exec-oracle--${failed ? "fail" : "ok"}`}
      role="status"
    >
      <span className="work-exec-oracle__badge">
        {oracleStatusLabel(status)}
      </span>
      {retryCount ? (
        <span className="work-exec-oracle__meta">retry {retryCount}</span>
      ) : null}
      {checked ? (
        <span className="work-exec-oracle__meta">
          {formatExecutionTime(checked)}
        </span>
      ) : null}
      {detail ? (
        <span className="work-exec-oracle__detail" title={detail}>
          {detail}
        </span>
      ) : null}
      {failed ? (
        <button
          type="button"
          className="plan-card__btn work-exec-oracle__action"
          disabled={busy || retryLimitReached}
          title={
            retryLimitReached
              ? "Oracle 수정 재시도 상한(2회)에 도달했습니다."
              : undefined
          }
          onClick={() => onReverify(row.id)}
        >
          {retryLimitReached
            ? "수정 재시도 상한 도달"
            : "에이전트에게 수정 요청"}
        </button>
      ) : null}
    </div>
  );
}

export function execStatusKey(status: string | undefined): string {
  if (!status) return "review";
  if (status === "review_required" || status === "pending_approval")
    return "review";
  if (status === "merge_conflict") return "rejected";
  return status.replace("_required", "");
}

export function WorktreePendingBanner({ row }: { row: PlanExecutionRecord }) {
  const lines = worktreeBannerLines(row);
  if (!isWorktreeExecution(row)) return null;
  return (
    <div className="exec-meta" role="status">
      {lines.branch ? (
        <span className="exec-meta__item">
          <WorkPlanIcon name="gitMerge" size={13} />
          <code>{lines.branch}</code>
        </span>
      ) : null}
      {lines.base ? (
        <span className="exec-meta__item">
          기준 <code>{lines.base}</code>
        </span>
      ) : null}
      {lines.commit ? (
        <span className="exec-meta__item exec-meta__commit">
          <code>{lines.commit.slice(0, 7)}</code>
        </span>
      ) : null}
    </div>
  );
}

export function ApplyIsolationBanner({ row }: { row: PlanExecutionRecord }) {
  if (
    row.isolation_effective !== "apply" &&
    row.isolation_effective !== "snapshot_override"
  ) {
    return null;
  }
  return (
    <div className="exec-banner" role="status">
      <span className="exec-banner__title">
        {row.isolation_effective === "snapshot_override"
          ? "비격리 snapshot override"
          : "Apply 실행"}
      </span>
      <span className="exec-banner__line">
        git merge 없음 · 승인 시 현재 작업 폴더 변경을 유지합니다.
      </span>
    </div>
  );
}

export function actionKey(
  item: Pick<PlanActionItem, "kind" | "index" | "recommended">,
): string {
  const kind = item.kind ?? (item.recommended ? "now" : "roadmap");
  return `${kind}:${item.index}`;
}

export function parseActionKey(
  key: string,
): { kind: string; index: number } | null {
  const sep = key.indexOf(":");
  if (sep <= 0) return null;
  const kind = key.slice(0, sep);
  const index = Number(key.slice(sep + 1));
  if (!Number.isFinite(index) || index < 1) return null;
  return { kind, index };
}

type DiffHunk = {
  id: string;
  ref: string;
  lineStart: number;
  lineEnd: number;
};

export function diffHunks(diff: string | undefined): DiffHunk[] {
  const lines = (diff ?? "").split("\n");
  const hunks: DiffHunk[] = [];
  for (let index = 0; index < lines.length; index += 1) {
    const ref = lines[index];
    if (!ref.startsWith("@@")) continue;
    let end = lines.length;
    for (let next = index + 1; next < lines.length; next += 1) {
      if (
        lines[next].startsWith("@@") ||
        lines[next].startsWith("diff --git ")
      ) {
        end = next;
        break;
      }
    }
    hunks.push({
      id: `${index + 1}:${ref}`,
      ref,
      lineStart: index + 1,
      lineEnd: end,
    });
  }
  return hunks;
}

export const EXECUTION_HISTORY_LIMIT = 5;
const MAX_VERIFY_RETRIES = 2;

export function openBlockObjectionsForAction(
  run: Record<string, unknown> | undefined,
  actionIndex: number | undefined,
): RoomObjection[] {
  if (actionIndex == null) return [];
  const rows = run?.objections;
  if (!Array.isArray(rows)) return [];
  return (rows as RoomObjection[]).filter(
    (o) =>
      o.status === "open" &&
      o.act === "BLOCK" &&
      o.plan_action_index === actionIndex,
  );
}

export function PlanObjectionAlert({
  title,
  message,
  objections,
  onFocusObjection,
  sessionIdForObjections,
  onObjectionResolved,
}: {
  title: string;
  message?: string;
  objections: RoomObjection[];
  onFocusObjection?: (objectionId: string, actionIndex?: number) => void;
  sessionIdForObjections?: string;
  onObjectionResolved?: () => void;
}) {
  const [busyId, setBusyId] = useState<string | null>(null);

  async function resolveObjection(
    objection: RoomObjection,
    verdict: "accepted" | "wontfix",
  ) {
    if (!sessionIdForObjections) return;
    setBusyId(objection.id);
    try {
      await resolveSessionObjection(
        sessionIdForObjections,
        objection.id,
        verdict,
      );
      onObjectionResolved?.();
    } finally {
      setBusyId(null);
    }
  }

  if (!objections.length) return null;
  return (
    <div className="work-exec-objection-alert" role="alert">
      <strong>{title}</strong>
      {message ? <p>{message}</p> : null}
      <ul>
        {objections.slice(0, 4).map((o) => (
          <li key={o.id}>
            <span>
              {o.from} · {o.act}
              {o.plan_action_index != null
                ? ` · plan #${o.plan_action_index}`
                : ""}
            </span>
            <span>{o.body}</span>
            {sessionIdForObjections && o.status === "open" ? (
              <>
                <button
                  type="button"
                  className="plan-btn"
                  disabled={busyId === o.id}
                  onClick={() => void resolveObjection(o, "accepted")}
                >
                  수용
                </button>
                <button
                  type="button"
                  className="plan-btn plan-btn--ghost"
                  disabled={busyId === o.id}
                  onClick={() => void resolveObjection(o, "wontfix")}
                >
                  기각
                </button>
              </>
            ) : onFocusObjection ? (
              <button
                type="button"
                className="plan-btn"
                onClick={() => onFocusObjection(o.id, o.plan_action_index)}
              >
                이의 해결
              </button>
            ) : null}
          </li>
        ))}
      </ul>
    </div>
  );
}
