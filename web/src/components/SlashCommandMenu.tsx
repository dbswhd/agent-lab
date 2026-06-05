import { useEffect, useMemo, useRef, useState } from "react";
import type { SlashCommandRecord } from "../api/client";

type Props = {
  value: string;
  commands: SlashCommandRecord[];
  onSelect: (slash: string) => void;
  onExecute: (command: SlashCommandRecord) => void;
  disabled?: boolean;
};

export function SlashCommandMenu({
  value,
  commands,
  onSelect,
  onExecute,
  disabled,
}: Props) {
  const open = !disabled && value.startsWith("/");
  const query = value.slice(1).split(/\s/)[0]?.toLowerCase() ?? "";
  const [highlight, setHighlight] = useState(0);
  const listRef = useRef<HTMLUListElement>(null);

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
    setHighlight(0);
  }, [query, open]);

  if (!open) return null;

  return (
    <div className="slash-command-menu" data-testid="slash-command-menu">
      <ul className="slash-command-menu__list" ref={listRef} role="listbox">
        {filtered.map((cmd, index) => (
          <li key={cmd.id}>
            <button
              type="button"
              className={[
                "slash-command-menu__item",
                index === highlight ? "is-active" : "",
                cmd.enabled === false ? "is-disabled" : "",
              ]
                .filter(Boolean)
                .join(" ")}
              role="option"
              aria-selected={index === highlight}
              onMouseEnter={() => setHighlight(index)}
              onClick={() => {
                onSelect(cmd.slash);
                onExecute(cmd);
              }}
            >
              <span className="slash-command-menu__slash">{cmd.slash}</span>
              <span className="slash-command-menu__body">
                <span className="slash-command-menu__label">{cmd.label}</span>
                {cmd.description ? (
                  <span className="slash-command-menu__desc">{cmd.description}</span>
                ) : null}
              </span>
              {cmd.agent ? (
                <span className="slash-command-menu__agent">{cmd.agent}</span>
              ) : null}
            </button>
          </li>
        ))}
        {filtered.length === 0 ? (
          <li className="slash-command-menu__empty">일치하는 명령 없음</li>
        ) : null}
      </ul>
    </div>
  );
}

export function slashMenuKeyDown(
  e: React.KeyboardEvent,
  filtered: SlashCommandRecord[],
  highlight: number,
  setHighlight: (n: number) => void,
  onPick: (cmd: SlashCommandRecord) => void,
): boolean {
  if (filtered.length === 0) return false;
  if (e.key === "ArrowDown") {
    e.preventDefault();
    setHighlight((highlight + 1) % filtered.length);
    return true;
  }
  if (e.key === "ArrowUp") {
    e.preventDefault();
    setHighlight((highlight - 1 + filtered.length) % filtered.length);
    return true;
  }
  if (e.key === "Tab" && filtered[highlight]) {
    e.preventDefault();
    onPick(filtered[highlight]);
    return true;
  }
  return false;
}
