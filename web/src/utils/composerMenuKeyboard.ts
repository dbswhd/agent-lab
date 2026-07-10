export type ComposerMenuKind = "mention" | "slash";

export type ComposerMenuKeyAction =
  | { type: "cycleMentionHighlight"; delta: number }
  | { type: "cycleSlashHighlight"; delta: number }
  | { type: "pageSlashHighlight"; direction: "up" | "down" }
  | { type: "pickMention" }
  | { type: "pickSlash" }
  | { type: "cancelMention" }
  | { type: "cancelSlash" }
  | { type: "send" };

export type ComposerMenuKeyResolution =
  | { handled: false }
  | { handled: true; preventDefault: true; action: ComposerMenuKeyAction };

export const SLASH_PAGE_SIZE = 10;

export function cycleMenuIndex(
  current: number,
  length: number,
  delta: number,
): number {
  if (length <= 0) return 0;
  return (current + delta + length) % length;
}

export function pageSlashHighlight(
  current: number,
  length: number,
  pageSize: number,
  direction: "up" | "down",
): number {
  if (length <= 0) return 0;
  if (direction === "down") {
    return Math.min(current + pageSize, length - 1);
  }
  return Math.max(current - pageSize, 0);
}

export function slashTokenOnly(value: string): boolean {
  return /^\/\S*$/.test(value);
}

export function resolveActiveComposerMenu(input: {
  mentionQuery: string | null;
  mentionOptionCount: number;
  value: string;
  slashOptionCount: number;
}): ComposerMenuKind | null {
  if (input.mentionQuery != null && input.mentionOptionCount > 0) {
    return "mention";
  }
  if (input.value.startsWith("/") && input.slashOptionCount > 0) {
    return "slash";
  }
  return null;
}

/** Remove leading `/token` draft; keep trailing message body. */
export function cancelSlashDraft(value: string): string {
  if (!value.startsWith("/")) return value;
  return value.replace(/^\/\S*\s?/, "").trimStart();
}

/** Remove incomplete `@token` at cursor; preserve surrounding text. */
export function cancelMentionAtCursor(
  value: string,
  cursor: number,
): { value: string; cursor: number } {
  const head = value.slice(0, cursor);
  const tail = value.slice(cursor);
  const newHead = head.replace(/(?:^|\s)@([^\s@]*)$/, (match) => {
    if (match.startsWith(" @")) return " ";
    return "";
  });
  return { value: newHead + tail, cursor: newHead.length };
}

export function resolveComposerMenuKeyDown(input: {
  key: string;
  shiftKey: boolean;
  value: string;
  mentionQuery: string | null;
  mentionOptionCount: number;
  slashOptionCount: number;
  cursor: number;
}): ComposerMenuKeyResolution {
  const active = resolveActiveComposerMenu({
    mentionQuery: input.mentionQuery,
    mentionOptionCount: input.mentionOptionCount,
    value: input.value,
    slashOptionCount: input.slashOptionCount,
  });

  if (active === "mention") {
    if (input.key === "ArrowDown") {
      return {
        handled: true,
        preventDefault: true,
        action: { type: "cycleMentionHighlight", delta: 1 },
      };
    }
    if (input.key === "ArrowUp") {
      return {
        handled: true,
        preventDefault: true,
        action: { type: "cycleMentionHighlight", delta: -1 },
      };
    }
    if (input.key === "Tab" || input.key === "Enter") {
      if (input.key === "Enter" && input.shiftKey) {
        return { handled: false };
      }
      return {
        handled: true,
        preventDefault: true,
        action: { type: "pickMention" },
      };
    }
    if (input.key === "Escape") {
      return {
        handled: true,
        preventDefault: true,
        action: { type: "cancelMention" },
      };
    }
    return { handled: false };
  }

  if (active === "slash") {
    if (input.key === "ArrowDown") {
      return {
        handled: true,
        preventDefault: true,
        action: { type: "cycleSlashHighlight", delta: 1 },
      };
    }
    if (input.key === "ArrowUp") {
      return {
        handled: true,
        preventDefault: true,
        action: { type: "cycleSlashHighlight", delta: -1 },
      };
    }
    if (input.key === "PageDown") {
      return {
        handled: true,
        preventDefault: true,
        action: { type: "pageSlashHighlight", direction: "down" },
      };
    }
    if (input.key === "PageUp") {
      return {
        handled: true,
        preventDefault: true,
        action: { type: "pageSlashHighlight", direction: "up" },
      };
    }
    if (input.key === "Tab" || input.key === "Enter") {
      if (input.key === "Enter" && input.shiftKey) {
        return { handled: false };
      }
      if (slashTokenOnly(input.value)) {
        return {
          handled: true,
          preventDefault: true,
          action: { type: "pickSlash" },
        };
      }
      if (input.key === "Enter") {
        return {
          handled: true,
          preventDefault: true,
          action: { type: "send" },
        };
      }
      return { handled: false };
    }
    if (input.key === "Escape") {
      return {
        handled: true,
        preventDefault: true,
        action: { type: "cancelSlash" },
      };
    }
    return { handled: false };
  }

  if (input.key === "Enter" && !input.shiftKey) {
    return {
      handled: true,
      preventDefault: true,
      action: { type: "send" },
    };
  }

  return { handled: false };
}
