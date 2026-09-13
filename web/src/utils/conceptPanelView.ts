/** Concept panel view model (RI-08).
 *
 * All of the panel's decidable behaviour lives here so it can be tested the way
 * the rest of this repo tests things — plain vitest, no DOM. `ConceptPanel.tsx`
 * stays a thin renderer over these.
 */

export type IdeationOption = {
  id: string;
  agent?: string;
  title?: string;
  principle?: string;
  usage?: string;
  difference?: string;
  tradeoff?: string;
  first_experiment?: string;
  raw?: string;
  parse_error?: string;
};

export type IdeationSelection = {
  option_id: string;
  parent_ids?: string[];
  title?: string;
  reason?: string;
  source_revision?: number;
};

export type IdeationDecision = {
  kind: "select" | "combine" | "reject" | "reopen" | string;
  option_id?: string;
  parent_ids?: string[];
  reason?: string;
  revision?: number;
  ts?: string;
};

export type IdeationState = {
  schema_version: number;
  revision: number;
  stage: "explore" | "shape" | "plan";
  brief?: Record<string, unknown>;
  options?: IdeationOption[];
  selection?: IdeationSelection | null;
  decisions?: IdeationDecision[];
};

export type ConceptPanelStatus =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "absent" }
  | { kind: "stale"; currentRevision: number; message: string }
  | { kind: "busy"; message: string }
  | { kind: "error"; message: string };

export type CandidateRow = {
  id: string;
  title: string;
  agent: string;
  /** Section lines the user compares candidates on; empty ones are dropped. */
  fields: Array<{ label: string; value: string }>;
  selected: boolean;
  rejected: boolean;
  /** Present when the model's reply could not be parsed into sections. */
  unparsedText: string | null;
};

const FIELD_LABELS: Array<[keyof IdeationOption, string]> = [
  ["principle", "작동 원리"],
  ["usage", "사용 장면"],
  ["difference", "다른 점"],
  ["tradeoff", "포기하는 것"],
  ["first_experiment", "첫 실험"],
];

export function rejectedOptionIds(state: IdeationState | null): string[] {
  const out: string[] = [];
  for (const decision of state?.decisions ?? []) {
    if (decision.kind !== "reject") continue;
    const id = decision.option_id ?? "";
    if (id && !out.includes(id)) out.push(id);
  }
  return out;
}

export function selectedOptionId(state: IdeationState | null): string | null {
  const id = state?.selection?.option_id ?? "";
  return id || null;
}

/** Candidate rows in stored order — never re-sorted by any quality score. */
export function buildCandidateRows(
  state: IdeationState | null,
): CandidateRow[] {
  const rejected = rejectedOptionIds(state);
  const selected = selectedOptionId(state);
  return (state?.options ?? []).map((option) => {
    const fields = FIELD_LABELS.map(([key, label]) => ({
      label,
      value: String(option[key] ?? "").trim(),
    })).filter((field) => field.value.length > 0);
    return {
      id: option.id,
      title: String(option.title ?? "").trim() || option.id,
      agent: String(option.agent ?? ""),
      fields,
      selected: option.id === selected,
      rejected: rejected.includes(option.id),
      // A candidate we could not parse still has to be readable, not hidden.
      unparsedText: option.parse_error ? String(option.raw ?? "") : null,
    };
  });
}

/** The selection shown when it is a combination with no stored option row. */
export function combinedSelectionRow(
  state: IdeationState | null,
): { id: string; title: string; parents: string[]; reason: string } | null {
  const selection = state?.selection;
  if (!selection) return null;
  const parents = selection.parent_ids ?? [];
  if (parents.length === 0) return null;
  return {
    id: selection.option_id,
    title: String(selection.title ?? "").trim() || selection.option_id,
    parents,
    reason: String(selection.reason ?? ""),
  };
}

export type StageView = {
  stage: IdeationState["stage"];
  /** §4.2 labels — never `APPROVED` / `VERIFIED`. */
  label: string;
  hint: string;
};

const STAGE_VIEWS: Record<IdeationState["stage"], StageView> = {
  explore: {
    stage: "explore",
    label: "구상 비교 중",
    hint: "마음에 드는 방향을 고르거나, 둘을 합치거나, 다른 접근을 요청하세요.",
  },
  shape: {
    stage: "shape",
    label: "구상 선택",
    hint: "고른 방향을 구체화하는 중입니다. 조건이 바뀌면 대화로 알려주세요.",
  },
  plan: {
    stage: "plan",
    label: "계획 준비됨",
    hint: "계획을 복사해 외부 에이전트에서 첫 작업을 시작할 수 있습니다.",
  },
};

export function stageView(state: IdeationState | null): StageView | null {
  if (!state) return null;
  return STAGE_VIEWS[state.stage] ?? null;
}

/** Map a failed PATCH into something the panel can show. */
export function statusFromError(error: unknown): ConceptPanelStatus {
  const err = error as {
    status?: number;
    code?: string;
    message?: string;
    currentRevision?: number;
  } | null;
  if (!err) return { kind: "error", message: "요청 실패" };
  if (err.status === 404) return { kind: "absent" };
  if (err.code === "stale_revision") {
    return {
      kind: "stale",
      currentRevision: Number(err.currentRevision ?? 0),
      message: "다른 곳에서 구상이 바뀌었습니다. 최신 후보를 확인하세요.",
    };
  }
  if (err.code === "busy") {
    return {
      kind: "busy",
      message: "이 세션이 지금 턴을 돌리는 중입니다. 끝난 뒤 다시 시도하세요.",
    };
  }
  return { kind: "error", message: String(err.message ?? "요청 실패") };
}

/** The status a reload should land on.
 *
 * A stale reload has to keep saying why the candidates just changed under the
 * user. Resetting to idle here is what made the refusal invisible: the notice
 * was set and then wiped by the reload it triggered.
 */
export function statusAfterReload(
  keepStatus?: ConceptPanelStatus,
): ConceptPanelStatus {
  return keepStatus?.kind === "stale" ? keepStatus : { kind: "idle" };
}

/** A stale response is only resolved by reloading — not by retrying the write. */
export function shouldReloadAfter(status: ConceptPanelStatus): boolean {
  return status.kind === "stale";
}

export type IdeationExportView = {
  revision: number;
  filename: string;
  markdown: string;
  /** Reasons the user should read the document before handing it over. */
  warnings: string[];
};

export function exportView(data: {
  revision: number;
  filename: string;
  markdown: string;
  plan_stale: boolean;
  open_blocks: number;
}): IdeationExportView {
  const warnings: string[] = [];
  // Both of these are in the document too — surfaced here so the user sees
  // them before copying, not after pasting.
  if (data.plan_stale) {
    warnings.push("계획이 최신 구상보다 오래됐습니다.");
  }
  if (data.open_blocks > 0) {
    warnings.push(`미결 BLOCK ${data.open_blocks}건이 문서에 포함됩니다.`);
  }
  return {
    revision: data.revision,
    filename: data.filename,
    markdown: data.markdown,
    warnings,
  };
}

export type SelectCommand = {
  command: "select" | "combine" | "reject" | "reset";
  option_id?: string;
  parent_ids?: string[];
  new_id?: string;
  reason?: string;
  expected_revision: number;
  request_id: string;
};

export function buildSelectCommand(args: {
  optionId: string;
  revision: number;
  requestId: string;
  reason?: string;
}): SelectCommand {
  return {
    command: "select",
    option_id: args.optionId,
    reason: args.reason ?? "",
    expected_revision: args.revision,
    request_id: args.requestId,
  };
}

export function buildCombineCommand(args: {
  parentIds: string[];
  revision: number;
  requestId: string;
  reason?: string;
}): SelectCommand {
  const parents = args.parentIds.filter(Boolean);
  return {
    command: "combine",
    parent_ids: parents,
    // Deterministic id so a retry of the same combination is a duplicate,
    // not a second candidate.
    new_id: combinedOptionId(parents),
    reason: args.reason ?? "",
    expected_revision: args.revision,
    request_id: args.requestId,
  };
}

export function combinedOptionId(parentIds: string[]): string {
  return `opt-combined-${parentIds.join("-")}`.slice(0, 64);
}

export function buildRejectCommand(args: {
  optionId: string;
  revision: number;
  requestId: string;
  reason?: string;
}): SelectCommand {
  return {
    command: "reject",
    option_id: args.optionId,
    reason: args.reason ?? "",
    expected_revision: args.revision,
    request_id: args.requestId,
  };
}

export function buildResetCommand(args: {
  revision: number;
  requestId: string;
  reason?: string;
}): SelectCommand {
  return {
    command: "reset",
    reason: args.reason ?? "",
    expected_revision: args.revision,
    request_id: args.requestId,
  };
}

/** Stable per-action request id — the same action retried reuses it. */
export function actionRequestId(
  sessionId: string,
  revision: number,
  action: string,
): string {
  return `${sessionId}:${revision}:${action}`;
}

export type KeyboardIntent =
  | { kind: "move"; index: number }
  | { kind: "toggleCompare" }
  | { kind: "select" }
  | { kind: "reject" }
  | { kind: "none" };

/** Roving focus + activation, so candidates are comparable without a mouse. */
export function keyboardIntent(args: {
  key: string;
  index: number;
  count: number;
}): KeyboardIntent {
  const { key, index, count } = args;
  if (count <= 0) return { kind: "none" };
  const clamp = (next: number) => Math.max(0, Math.min(count - 1, next));
  switch (key) {
    case "ArrowDown":
    case "ArrowRight":
      return { kind: "move", index: clamp(index + 1) };
    case "ArrowUp":
    case "ArrowLeft":
      return { kind: "move", index: clamp(index - 1) };
    case "Home":
      return { kind: "move", index: 0 };
    case "End":
      return { kind: "move", index: count - 1 };
    case "Enter":
    case " ":
      return { kind: "select" };
    case "c":
    case "C":
      return { kind: "toggleCompare" };
    case "x":
    case "X":
    case "Delete":
      return { kind: "reject" };
    default:
      return { kind: "none" };
  }
}
