import { Fragment, type ReactNode } from "react";

/** Slash command or @mention token at compose time — Progress blue. */
const COMPOSER_TRIGGER_TOKEN_RE =
  /(\/[A-Za-z0-9][A-Za-z0-9_-]*|@[A-Za-z][A-Za-z0-9_./-]*)/g;

function isSlashTrigger(value: string, start: number): boolean {
  const lineStart = value.lastIndexOf("\n", start - 1) + 1;
  return start === lineStart;
}

function isMentionTrigger(value: string, start: number): boolean {
  if (start === 0) return true;
  return /\s/.test(value[start - 1] ?? "");
}

export function buildComposerHighlightNodes(value: string): ReactNode[] {
  if (!value) return [];

  const nodes: ReactNode[] = [];
  let last = 0;
  let match: RegExpExecArray | null;

  COMPOSER_TRIGGER_TOKEN_RE.lastIndex = 0;
  while ((match = COMPOSER_TRIGGER_TOKEN_RE.exec(value)) !== null) {
    const token = match[1] ?? "";
    const start = match.index;
    if (!token) continue;

    const isSlash = token.startsWith("/");
    const isMention = token.startsWith("@");
    if (isSlash && !isSlashTrigger(value, start)) continue;
    if (isMention && !isMentionTrigger(value, start)) continue;

    if (start > last) {
      nodes.push(
        <Fragment key={`t-${last}`}>{value.slice(last, start)}</Fragment>,
      );
    }
    nodes.push(
      <span key={`tok-${start}`} className="composer-input__token">
        {token}
      </span>,
    );
    last = start + token.length;
  }

  if (last < value.length) {
    nodes.push(<Fragment key={`t-${last}`}>{value.slice(last)}</Fragment>);
  }

  return nodes.length > 0 ? nodes : [value];
}
