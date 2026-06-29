export type TurnItem =
  | {
      readonly id: string;
      readonly kind: "final_output";
      readonly text: string;
    }
  | {
      readonly id: string;
      readonly kind:
        | "reasoning_summary"
        | "activity"
        | "command"
        | "file_change";
      readonly text: string;
      readonly status: "running" | "done";
    }
  | {
      readonly id: string;
      readonly kind: "tool";
      readonly tool: string;
      readonly args?: string;
      readonly output?: string;
      readonly startedAt: number;
      readonly doneAt?: number;
    }
  | {
      readonly id: string;
      readonly kind: "error";
      readonly text: string;
    };

export type TurnItemEvent = Record<string, unknown> & {
  readonly type?: string;
};

function normalizeActivity(
  text: string,
): { kind: "reasoning_summary" | "activity"; text: string } {
  const trimmed = text.trim();
  if (trimmed.startsWith("[thinking]")) {
    const body = trimmed.slice("[thinking]".length).trim();
    return { kind: "reasoning_summary", text: body || trimmed };
  }
  return { kind: "activity", text: trimmed };
}

function toolFingerprint(tool: string, args?: string): string {
  return `${tool}|${(args ?? "").trim()}`;
}

function upsertReasoning(
  items: TurnItem[],
  text: string,
  now: number,
): TurnItem[] {
  for (let index = items.length - 1; index >= 0; index -= 1) {
    const item = items[index];
    if (item?.kind === "reasoning_summary") {
      if (item.text === text) return items;
      items[index] = { ...item, text, status: "running" };
      return items;
    }
  }
  return [
    ...items,
    {
      id: `reasoning-${now}-${items.length}`,
      kind: "reasoning_summary",
      text,
      status: "running",
    },
  ].slice(-24) as TurnItem[];
}

function upsertStatusActivity(
  items: TurnItem[],
  text: string,
): TurnItem[] | null {
  const prefixes = [
    "Codex 대기 중…",
    "Codex 응답 대기…",
    "Codex exec",
    "Codex turn",
    "Codex OAuth",
    "Codex proxy",
    "Codex stderr",
  ];
  if (!prefixes.some((prefix) => text.startsWith(prefix))) {
    return null;
  }
  for (let index = items.length - 1; index >= 0; index -= 1) {
    const item = items[index];
    if (item?.kind !== "activity") continue;
    if (!prefixes.some((prefix) => item.text.startsWith(prefix))) continue;
    if (item.text === text) return items;
    const next = [...items];
    next[index] = { ...item, text, status: "running" };
    return next;
  }
  return null;
}

export function reduceTurnItems(
  current: readonly TurnItem[] | undefined,
  event: TurnItemEvent,
  now = Date.now(),
): TurnItem[] {
  const items = [...(current ?? [])];
  const type = String(event.type ?? "");
  if (
    (type === "agent_activity" || type === "reasoning_summary") &&
    typeof event.text === "string" &&
    event.text.trim()
  ) {
    const normalized =
      type === "reasoning_summary"
        ? { kind: "reasoning_summary" as const, text: event.text.trim() }
        : normalizeActivity(event.text);
    if (normalized.kind === "reasoning_summary") {
      return upsertReasoning(items, normalized.text, now);
    }
    const upserted = upsertStatusActivity(items, normalized.text);
    if (upserted) {
      return upserted.slice(-24) as TurnItem[];
    }
    const last = items.at(-1);
    if (
      last?.kind === normalized.kind &&
      "text" in last &&
      last.text === normalized.text
    ) {
      return items;
    }
    return [
      ...items,
      {
        id: `${normalized.kind}-${now}-${items.length}`,
        kind: normalized.kind,
        text: normalized.text,
        status: "running",
      },
    ].slice(-24) as TurnItem[];
  }
  if (type === "tool_start") {
    const tool = String(event.tool ?? "tool");
    const argsObj = event.args as Record<string, unknown> | undefined;
    const target =
      typeof argsObj?.target === "string" ? argsObj.target : undefined;
    const fp = toolFingerprint(tool, target);
    for (let index = items.length - 1; index >= 0; index -= 1) {
      const item = items[index];
      if (item?.kind === "tool" && !item.doneAt) {
        if (toolFingerprint(item.tool, item.args) === fp) return items;
        break;
      }
    }
    return [
      ...items,
      {
        id: `tool-${tool}-${now}-${items.length}`,
        kind: "tool",
        tool,
        args: target,
        startedAt: now,
      },
    ].slice(-24) as TurnItem[];
  }
  if (type === "tool_output") {
    const tool = String(event.tool ?? "tool");
    const chunk = String(event.chunk ?? "");
    if (!chunk) return items;
    for (let index = items.length - 1; index >= 0; index -= 1) {
      const item = items[index];
      if (item?.kind === "tool" && item.tool === tool && !item.doneAt) {
        items[index] = {
          ...item,
          output: `${item.output ?? ""}${chunk}`.slice(-4000),
        };
        break;
      }
    }
    return items;
  }
  if (type === "tool_done") {
    const tool = String(event.tool ?? "tool");
    for (let index = items.length - 1; index >= 0; index -= 1) {
      const item = items[index];
      if (item?.kind === "tool" && item.tool === tool && !item.doneAt) {
        items[index] = { ...item, doneAt: now };
        break;
      }
    }
    return items.map((item) =>
      item.kind !== "tool" && "status" in item
        ? { ...item, status: "done" as const }
        : item,
    );
  }
  if (type === "agent_done") {
    return items.map((item) =>
      item.kind !== "tool" && "status" in item
        ? { ...item, status: "done" as const }
        : item,
    );
  }
  if (type === "agent_error") {
    const text = String(event.message ?? event.note ?? "Agent error");
    return [
      ...items.map((item) =>
        item.kind !== "tool" && "status" in item
          ? { ...item, status: "done" as const }
          : item,
      ),
      { id: `error-${now}`, kind: "error", text },
    ];
  }
  return items;
}
