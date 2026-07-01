import type { PlanActionItem, PlanExecutionRecord } from "../api/client";
import { parseDiffStat } from "./diffStatFormat";
import { parsePlanField } from "./planTextFormat";

export type PlanTodoItemStatus = "done" | "active" | "pending" | "gate";

export type PlanTodoRow = {
  key: string;
  item: PlanActionItem;
  status: PlanTodoItemStatus;
  label: string;
  where?: string;
  verify?: string;
  selectable: boolean;
};

export type PlanDiffRollup = {
  fileCount: number;
  adds: number;
  dels: number;
};

export type PlanTodoProgress = {
  current: number;
  total: number;
};

const DONE_STATUSES = new Set(["merged", "completed", "review_required"]);

function planItemKey(
  item: Pick<PlanActionItem, "kind" | "index" | "recommended">,
): string {
  const kind = item.kind ?? (item.recommended ? "now" : "roadmap");
  return `${kind}:${item.index}`;
}

function fieldBody(value: string | undefined | null): string {
  return parsePlanField(value)?.body ?? "";
}

function completedActionIndices(
  executions: PlanExecutionRecord[],
): Set<number> {
  const done = new Set<number>();
  for (const row of executions) {
    if (row.action_index == null) continue;
    if (DONE_STATUSES.has(String(row.status ?? ""))) {
      done.add(row.action_index);
    }
  }
  return done;
}

function orderedPlanItems(
  recommended: PlanActionItem | null,
  nowItems: PlanActionItem[],
  roadmap: PlanActionItem[],
): PlanActionItem[] {
  const items = [
    ...(recommended ? [recommended] : []),
    ...nowItems,
    ...roadmap,
  ];
  const seen = new Set<string>();
  return items.filter((item) => {
    const key = planItemKey(item);
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

export function rollupDiffStat(
  text: string | undefined | null,
): PlanDiffRollup {
  const parsed = text?.trim() ? parseDiffStat(text) : null;
  if (!parsed?.files.length) {
    return { fileCount: 0, adds: 0, dels: 0 };
  }
  return parsed.files.reduce(
    (acc, file) => ({
      fileCount: acc.fileCount + 1,
      adds: acc.adds + file.adds,
      dels: acc.dels + file.dels,
    }),
    { fileCount: 0, adds: 0, dels: 0 },
  );
}

export function resolvePlanDiffRollup(input: {
  activePending?: PlanExecutionRecord | null;
  executions?: PlanExecutionRecord[];
}): PlanDiffRollup {
  if (input.activePending?.diff_stat?.trim()) {
    return rollupDiffStat(input.activePending.diff_stat);
  }
  const rows = input.executions ?? [];
  for (let i = rows.length - 1; i >= 0; i -= 1) {
    const stat = rows[i]?.diff_stat;
    if (stat?.trim()) return rollupDiffStat(stat);
  }
  return { fileCount: 0, adds: 0, dels: 0 };
}

export function buildPlanTodoRows(input: {
  recommended: PlanActionItem | null;
  nowItems: PlanActionItem[];
  roadmap: PlanActionItem[];
  selectedKey: string | null;
  executions: PlanExecutionRecord[];
  activePending?: PlanExecutionRecord | null;
}): PlanTodoRow[] {
  const done = completedActionIndices(input.executions);
  const activeIndex =
    input.activePending?.action_index ??
    (input.selectedKey
      ? orderedPlanItems(input.recommended, input.nowItems, input.roadmap).find(
          (item) => planItemKey(item) === input.selectedKey,
        )?.index
      : undefined) ??
    input.recommended?.index;

  return orderedPlanItems(
    input.recommended,
    input.nowItems,
    input.roadmap,
  ).map((item) => {
    const key = planItemKey(item);
    const isGate = item.executable === false;
    const label = isGate
      ? fieldBody(item.summary || item.what)
      : fieldBody(item.what);
    let status: PlanTodoItemStatus = "pending";
    if (isGate) status = "gate";
    else if (done.has(item.index)) status = "done";
    else if (item.index === activeIndex) status = "active";

    return {
      key,
      item,
      status,
      label: label || fieldBody(item.what) || `#${item.index}`,
      where: fieldBody(item.where) || undefined,
      verify: fieldBody(item.verify) || undefined,
      selectable: !isGate,
    };
  });
}

export function planTodoProgress(
  rows: PlanTodoRow[],
  activePending?: PlanExecutionRecord | null,
): PlanTodoProgress {
  const total = rows.length || 1;
  if (!rows.length) return { current: 0, total: 0 };

  const activeIndex =
    activePending?.action_index ??
    rows.find((row) => row.status === "active")?.item.index;
  if (activeIndex == null) {
    const doneCount = rows.filter((row) => row.status === "done").length;
    return { current: Math.min(doneCount + 1, total), total };
  }

  const position = rows.findIndex((row) => row.item.index === activeIndex);
  return {
    current: position >= 0 ? position + 1 : 1,
    total,
  };
}

export function formatPlanTodoCollapsedSummary(
  progress: PlanTodoProgress,
  diff: PlanDiffRollup,
  locale: "en" | "ko",
): string {
  const ko = locale === "ko";
  const step =
    progress.total > 0
      ? ko
        ? `${progress.current}/${progress.total}단계`
        : `Step ${progress.current}/${progress.total}`
      : ko
        ? "0단계"
        : "Step 0";

  if (diff.fileCount <= 0) return step;

  const files = ko
    ? `${diff.fileCount}개 파일 변경됨`
    : `${diff.fileCount} file${diff.fileCount === 1 ? "" : "s"} changed`;

  return `${step} · ${files} +${diff.adds} -${diff.dels}`;
}
