import { useMemo, type RefObject } from "react";
import type { SlashCommandRecord } from "../api/client";
import { useDismissOnPointerDownOutside } from "../hooks/useDismissOnPointerDownOutside";

type Props = {
  value: string;
  commands: SlashCommandRecord[];
  onSelect: (slash: string) => void;
  onExecute: (command: SlashCommandRecord) => void;
  onDismiss?: () => void;
  /** Clicks inside this region (composer capsule) do not dismiss the menu. */
  insideRef?: RefObject<Node | null>;
  disabled?: boolean;
  highlightedIndex?: number;
  onHighlightChange?: (index: number) => void;
};

/** Slash autocomplete — prototype `.slash-menu` / `.slash-item` (surfaces.css). */
export function SlashCommandMenu({
  value,
  commands,
  onSelect,
  onExecute,
  onDismiss,
  insideRef,
  disabled,
  highlightedIndex,
  onHighlightChange,
}: Props) {
  const open = !disabled && value.startsWith("/");
  const query = value.slice(1).split(/\s/)[0]?.toLowerCase() ?? "";
  const hi = highlightedIndex ?? 0;
  const menuRef = useDismissOnPointerDownOutside(
    open && !!onDismiss,
    onDismiss ?? (() => {}),
    undefined,
    insideRef,
  );

  const filtered = useMemo(() => {
    if (!open) return [];
    const rows = commands.filter((c) => c.enabled !== false);
    if (!query) return rows;
    return rows.filter(
      (c) =>
        c.slash.toLowerCase().includes(query) ||
        c.label.toLowerCase().includes(query) ||
        (c.description ?? "").toLowerCase().includes(query),
    );
  }, [commands, open, query]);

  if (!open) return null;

  return (
    <div
      className="slash-menu"
      ref={menuRef}
      data-testid="slash-command-menu"
      role="listbox"
      aria-label="slash commands"
    >
      {filtered.map((cmd, i) => (
        <button
          key={cmd.id}
          type="button"
          className={[
            "slash-item",
            i === hi ? "is-active" : "",
            cmd.enabled === false ? "is-disabled" : "",
          ]
            .filter(Boolean)
            .join(" ")}
          role="option"
          aria-selected={i === hi}
          disabled={cmd.enabled === false}
          onMouseEnter={() => onHighlightChange?.(i)}
          onClick={() => {
            if (cmd.enabled === false) return;
            onSelect(cmd.slash);
            onExecute(cmd);
          }}
        >
          <span className="slash-item__slash">{cmd.slash}</span>
          <span className="slash-item__label">
            {cmd.label}
            {cmd.description ? ` — ${cmd.description}` : ""}
            {cmd.enabled === false
              ? ` (${cmd.disabled_reason ?? "현재 세션에서 사용할 수 없음"})`
              : ""}
          </span>
        </button>
      ))}
      {filtered.length === 0 ? (
        <p className="slash-item slash-item--empty">일치하는 명령 없음</p>
      ) : null}
    </div>
  );
}
