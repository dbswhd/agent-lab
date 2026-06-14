import { useEffect, useMemo, useRef, useState } from "react";
import type { SlashCommandRecord } from "../api/client";

type Props = {
  value: string;
  commands: SlashCommandRecord[];
  onSelect: (slash: string) => void;
  onExecute: (command: SlashCommandRecord) => void;
  disabled?: boolean;
};

/** Slash autocomplete — prototype `.slash-menu` / `.slash-item` (surfaces.css). */
export function SlashCommandMenu({
  value,
  commands,
  onSelect,
  onExecute,
  disabled,
}: Props) {
  const open = !disabled && value.startsWith("/");
  const query = value.slice(1).split(/\s/)[0]?.toLowerCase() ?? "";
  const [hi, setHi] = useState(0);
  const listRef = useRef<HTMLDivElement>(null);

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

  useEffect(() => {
    setHi(0);
  }, [query, open]);

  if (!open) return null;

  return (
    <div
      className="slash-menu"
      ref={listRef}
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
          onMouseEnter={() => setHi(i)}
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
