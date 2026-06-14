/** Parse Human Inbox ref strings (L42, plan.md, task ids). */

export type InboxRefTarget =
  | { kind: "chat"; line: number }
  | { kind: "plan" }
  | { kind: "task"; taskId: string }
  | { kind: "unknown"; raw: string };

export function parseInboxRef(raw: string): InboxRefTarget {
  const ref = raw.trim();
  if (!ref) return { kind: "unknown", raw };
  const chatMatch = /^L?(\d+)$/i.exec(ref);
  if (chatMatch) {
    const line = Number.parseInt(chatMatch[1] ?? "", 10);
    if (line > 0) return { kind: "chat", line };
  }
  if (/^plan\.md$/i.test(ref) || ref.toLowerCase() === "plan") {
    return { kind: "plan" };
  }
  if (/^t[-_]/i.test(ref) || ref.startsWith("task:")) {
    return { kind: "task", taskId: ref.replace(/^task:/i, "") };
  }
  return { kind: "unknown", raw: ref };
}

export type InboxRefHandlers = {
  onChatLine?: (line: number) => void;
  onOpenPlan?: () => void;
  onFocusTask?: (taskId: string) => void;
};

export function activateInboxRef(
  ref: string,
  handlers: InboxRefHandlers,
): boolean {
  const target = parseInboxRef(ref);
  if (target.kind === "chat") {
    handlers.onChatLine?.(target.line);
    return true;
  }
  if (target.kind === "plan") {
    handlers.onOpenPlan?.();
    return true;
  }
  if (target.kind === "task") {
    handlers.onFocusTask?.(target.taskId);
    return true;
  }
  return false;
}
