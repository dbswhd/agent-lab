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
    const kind =
      type === "reasoning_summary" ? "reasoning_summary" : "activity";
    const text = event.text.trim();
    if (kind === "activity" && text.startsWith("[thinking]")) {
      for (let index = items.length - 1; index >= 0; index -= 1) {
        const item = items[index];
        if (
          item?.kind === "activity" &&
          "text" in item &&
          item.text.startsWith("[thinking]")
        ) {
          if (item.text === text) return items;
          items[index] = { ...item, text, status: "running" };
          return items;
        }
      }
    }
    const last = items.at(-1);
    if (last?.kind === kind && "text" in last && last.text === text)
      return items;
    return [
      ...items,
      { id: `${kind}-${now}-${items.length}`, kind, text, status: "running" },
    ].slice(-20) as TurnItem[];
  }
  if (type === "tool_start") {
    const tool = String(event.tool ?? "tool");
    const args = event.args as Record<string, unknown> | undefined;
    const target = typeof args?.target === "string" ? args.target : undefined;
    return [
      ...items,
      {
        id: `tool-${tool}-${now}-${items.length}`,
        kind: "tool",
        tool,
        args: target,
        startedAt: now,
      },
    ].slice(-20) as TurnItem[];
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
