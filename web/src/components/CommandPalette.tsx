import { useEffect, useMemo, useRef, useState } from "react";
import type { WorkspaceTab } from "../utils/workspaceTabs";
import { WORKSPACE_TABS } from "../utils/workspaceTabs";
import { COMMAND_PALETTE_EVENT } from "../utils/desktopShortcuts";

export type CommandAction = {
  id: string;
  label: string;
  hint?: string;
  run: () => void;
};

type Props = {
  actions: CommandAction[];
};

export function CommandPalette({ actions }: Props) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    function onOpen() {
      setOpen(true);
      setQuery("");
    }
    window.addEventListener(COMMAND_PALETTE_EVENT, onOpen);
    return () => window.removeEventListener(COMMAND_PALETTE_EVENT, onOpen);
  }, []);

  useEffect(() => {
    if (!open) return;
    const id = window.requestAnimationFrame(() => inputRef.current?.focus());
    return () => window.cancelAnimationFrame(id);
  }, [open]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return actions;
    return actions.filter(
      (a) =>
        a.label.toLowerCase().includes(q) ||
        a.hint?.toLowerCase().includes(q),
    );
  }, [actions, query]);

  if (!open) return null;

  return (
    <div
      className="command-palette-backdrop"
      role="presentation"
      onClick={() => setOpen(false)}
    >
      <div
        className="command-palette"
        role="dialog"
        aria-label="Command palette"
        onClick={(e) => e.stopPropagation()}
      >
        <input
          ref={inputRef}
          className="command-palette__input mac-textfield"
          value={query}
          placeholder="명령 검색…"
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Escape") setOpen(false);
            if (e.key === "Enter" && filtered[0]) {
              filtered[0].run();
              setOpen(false);
            }
          }}
        />
        <ul className="command-palette__list" role="listbox">
          {filtered.map((action) => (
            <li key={action.id}>
              <button
                type="button"
                className="command-palette__item"
                onClick={() => {
                  action.run();
                  setOpen(false);
                }}
              >
                <span>{action.label}</span>
                {action.hint ? (
                  <span className="command-palette__hint">{action.hint}</span>
                ) : null}
              </button>
            </li>
          ))}
          {filtered.length === 0 ? (
            <li className="command-palette__empty">일치하는 명령 없음</li>
          ) : null}
        </ul>
      </div>
    </div>
  );
}

export function workspacePaletteActions(
  onTab: (tab: WorkspaceTab) => void,
  extras: CommandAction[] = [],
): CommandAction[] {
  return [
    ...WORKSPACE_TABS.map((tab) => ({
      id: `tab-${tab.id}`,
      label: `Open ${tab.label}`,
      hint: tab.shortcut,
      run: () => onTab(tab.id),
    })),
    ...extras,
  ];
}
