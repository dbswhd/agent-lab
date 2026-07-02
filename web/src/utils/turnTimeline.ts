import type { TurnItem } from "./turnItems";

export type TurnActivityStats = {
  editedFiles: number;
  exploredFiles: number;
  searches: number;
  commands: number;
  linesAdded: number;
  linesRemoved: number;
};

function normalizeToolName(tool: string): string {
  return tool.trim().toLowerCase().replace(/[\s-]+/g, "_");
}

type ToolBucket = "command" | "search" | "edit" | "explore" | "other";

function classifyTool(tool: string): ToolBucket {
  const name = normalizeToolName(tool);
  if (
    /shell|bash|terminal|run_terminal|execute|command|cmd|process|npm|pytest|make/.test(
      name,
    )
  ) {
    return "command";
  }
  if (/grep|search|glob|find|rg|ripgrep|codebase|web_search|query|scout/.test(name)) {
    return "search";
  }
  if (
    /write|edit|patch|apply|str_replace|create|delete|rename|touch|notebook|multi_edit/.test(
      name,
    )
  ) {
    return "edit";
  }
  if (/read|list|ls|cat|view|explore|head|tail|file|tree|stat/.test(name)) {
    return "explore";
  }
  return "other";
}

function pathFromArgs(args?: string): string | null {
  const trimmed = args?.trim();
  if (!trimmed) return null;
  const first = trimmed.split(/\s+/)[0]?.replace(/^["'`]|["'`]$/g, "");
  return first && first.includes("/") ? first : trimmed.slice(0, 120);
}

function bumpDiffStats(output: string | undefined, stats: TurnActivityStats): void {
  if (!output) return;
  for (const line of output.split("\n")) {
    if (line.startsWith("+++") || line.startsWith("---")) continue;
    if (line.startsWith("+")) stats.linesAdded += 1;
    else if (line.startsWith("-")) stats.linesRemoved += 1;
  }
}

/** Cursor-style one-line activity summary from turn items. */
export function summarizeTurnItems(
  items: readonly TurnItem[],
  running = false,
): TurnActivityStats {
  const stats: TurnActivityStats = {
    editedFiles: 0,
    exploredFiles: 0,
    searches: 0,
    commands: 0,
    linesAdded: 0,
    linesRemoved: 0,
  };
  const editedPaths = new Set<string>();
  const exploredPaths = new Set<string>();

  for (const item of items) {
    if (item.kind === "file_change") {
      editedPaths.add(item.text.trim() || item.id);
      continue;
    }
    if (item.kind === "command") {
      stats.commands += 1;
      continue;
    }
    if (item.kind === "activity") {
      const text = item.text.toLowerCase();
      if (/edit|write|patch|apply|wrote|updated|saved/.test(text)) {
        editedPaths.add(item.text);
      } else if (/read|explor|list|scan|open|viewed|grep|search/.test(text)) {
        if (/search|grep|find/.test(text)) stats.searches += 1;
        else exploredPaths.add(item.text);
      } else if (/run|command|shell|execut/.test(text)) {
        stats.commands += 1;
      }
      continue;
    }
    if (item.kind !== "tool") continue;

    const bucket = classifyTool(item.tool);
    const path = pathFromArgs(item.args);
    if (bucket === "command") stats.commands += 1;
    else if (bucket === "search") stats.searches += 1;
    else if (bucket === "edit") {
      editedPaths.add(path ?? `${item.tool}:${item.args ?? item.id}`);
    } else if (bucket === "explore") {
      exploredPaths.add(path ?? `${item.tool}:${item.args ?? item.id}`);
    } else if (path) {
      exploredPaths.add(path);
    }

    if (item.doneAt) bumpDiffStats(item.output, stats);
  }

  stats.editedFiles = editedPaths.size;
  stats.exploredFiles = exploredPaths.size;

  if (
    running &&
    stats.editedFiles === 0 &&
    stats.exploredFiles === 0 &&
    stats.searches === 0 &&
    stats.commands === 0
  ) {
    const pendingTools = items.filter(
      (item) => item.kind === "tool" && !item.doneAt,
    ).length;
    if (pendingTools > 0) stats.commands = pendingTools;
  }

  return stats;
}

function plural(count: number, singular: string, pluralWord = `${singular}s`): string {
  return count === 1 ? singular : pluralWord;
}

export function formatTurnActivitySummary(
  stats: TurnActivityStats,
  running = false,
): string {
  const parts: string[] = [];
  if (stats.editedFiles > 0) {
    parts.push(
      `${running ? "Editing" : "Edited"} ${stats.editedFiles} ${plural(stats.editedFiles, "file")}`,
    );
  }
  if (stats.exploredFiles > 0) {
    parts.push(
      `${running ? "exploring" : "explored"} ${stats.exploredFiles} ${plural(stats.exploredFiles, "file")}`,
    );
  }
  if (stats.searches > 0) {
    parts.push(
      `${stats.searches} ${plural(stats.searches, "search", "searches")}`,
    );
  }
  if (stats.commands > 0) {
    parts.push(
      `${running ? "running" : "ran"} ${stats.commands} ${plural(stats.commands, "command")}`,
    );
  }
  if (parts.length === 0) {
    return running ? "Working…" : "No activity";
  }
  return parts.join(", ");
}

export function formatWorkedDuration(totalSeconds: number): string {
  const safe = Math.max(0, Math.floor(totalSeconds));
  const minutes = Math.floor(safe / 60);
  const seconds = safe % 60;
  if (minutes > 0) return `Worked for ${minutes}m ${seconds}s`;
  return `Worked for ${seconds}s`;
}

/** Elapsed wall time covered by tool steps (ms timestamps on TurnItems). */
export function turnItemsDurationSeconds(
  items: readonly TurnItem[],
  now = Date.now(),
): number | null {
  let start: number | null = null;
  let end: number | null = null;
  for (const item of items) {
    if (item.kind !== "tool") continue;
    start = start === null ? item.startedAt : Math.min(start, item.startedAt);
    end = Math.max(end ?? item.startedAt, item.doneAt ?? now);
  }
  if (start === null || end === null) return null;
  return Math.max(1, Math.round((end - start) / 1000));
}

export function truncateMiddle(text: string, max = 72): string {
  const t = text.trim();
  if (t.length <= max) return t;
  const head = Math.max(16, Math.floor(max * 0.45));
  const tail = max - head - 1;
  return `${t.slice(0, head)}…${t.slice(-tail)}`;
}

export function toolStepSummary(item: Extract<TurnItem, { kind: "tool" }>): string {
  const name = item.tool.trim() || "tool";
  const detail = item.args?.trim() ?? "";
  if (detail) {
    return item.doneAt
      ? `Ran ${name} · ${truncateMiddle(detail, 64)}`
      : `Running ${name} · ${truncateMiddle(detail, 64)}`;
  }
  return item.doneAt ? `Ran ${name}` : `Running ${name}…`;
}

export function reasoningStepSummary(item: {
  text: string;
  status: "running" | "done";
}): string {
  const preview = truncateMiddle(item.text, 56);
  return item.status === "running" ? `Thought · ${preview}` : `Thought · ${preview}`;
}

export function activityStepSummary(item: { text: string }): string {
  return truncateMiddle(item.text, 80);
}

export function stepDetailsOpen(item: TurnItem, running: boolean): boolean {
  if (item.kind === "tool") return !item.doneAt && running;
  if ("status" in item) return item.status === "running" && running;
  return false;
}

/** One-line description of the most recent step, for the collapsed timeline summary. */
export function latestStepSummary(
  steps: readonly TurnItem[],
): string | null {
  const last = steps.at(-1);
  if (!last) return null;
  if (last.kind === "tool") return toolStepSummary(last);
  if (last.kind === "reasoning_summary") return reasoningStepSummary(last);
  if (last.kind === "activity") return activityStepSummary(last);
  if (last.kind === "error") return last.text;
  return null;
}
