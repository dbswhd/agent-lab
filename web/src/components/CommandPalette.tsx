import { useEffect, useMemo, useRef, useState } from "react";
import type { CommandAction } from "../utils/commandPaletteActions";
import { COMMAND_PALETTE_EVENT } from "../utils/desktopShortcuts";

type Props = {
  actions: CommandAction[];
};

/** CommandPalette — canonical (⌘K).
 *
 *  Listens for COMMAND_PALETTE_EVENT (dispatched by desktopShortcuts).
 *  Renders with canonical .cmd-palette-* classes (overlays.css).
 *  Drop-in for the old component that used .command-palette-* (macos26.css).
 */
export function CommandPalette({ actions }: Props) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [activeIdx, setActiveIdx] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  /* open via event */
  useEffect(() => {
    function onOpen() {
      setOpen(true);
      setQuery("");
      setActiveIdx(0);
    }
    window.addEventListener(COMMAND_PALETTE_EVENT, onOpen);
    return () => window.removeEventListener(COMMAND_PALETTE_EVENT, onOpen);
  }, []);

  /* focus on open */
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
        a.label.toLowerCase().includes(q) || a.hint?.toLowerCase().includes(q),
    );
  }, [actions, query]);

  function pick(action: CommandAction) {
    action.run();
    setOpen(false);
  }

  function onKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Escape") {
      setOpen(false);
      return;
    }
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActiveIdx((v) => (v + 1) % Math.max(1, filtered.length));
    }
    if (e.key === "ArrowUp") {
      e.preventDefault();
      setActiveIdx(
        (v) => (v - 1 + filtered.length) % Math.max(1, filtered.length),
      );
    }
    if (e.key === "Enter" && filtered[activeIdx]) pick(filtered[activeIdx]);
  }

  if (!open) return null;

  return (
    <div
      className="cmd-palette-backdrop"
      role="presentation"
      onClick={() => setOpen(false)}
    >
      <div
        className="cmd-palette"
        role="dialog"
        aria-label="Command palette"
        onClick={(e) => e.stopPropagation()}
      >
        <input
          ref={inputRef}
          className="cmd-palette__input"
          value={query}
          placeholder="명령 검색… (⌘K)"
          onChange={(e) => {
            setQuery(e.target.value);
            setActiveIdx(0);
          }}
          onKeyDown={onKeyDown}
        />

        <ul className="cmd-palette__list" role="listbox">
          {filtered.map((action, i) => (
            <li key={action.id}>
              <button
                type="button"
                className={[
                  "cmd-palette__item",
                  action.danger ? "cmd-palette__item--danger" : "",
                  i === activeIdx ? "is-active" : "",
                ]
                  .filter(Boolean)
                  .join(" ")}
                role="option"
                aria-selected={i === activeIdx}
                onMouseEnter={() => setActiveIdx(i)}
                onClick={() => pick(action)}
              >
                <span className="cmd-palette__item-label">{action.label}</span>
                {action.hint ? (
                  <span className="cmd-palette__hint">
                    <kbd className="kbd">{action.hint}</kbd>
                  </span>
                ) : null}
              </button>
            </li>
          ))}
          {filtered.length === 0 ? (
            <li className="cmd-palette__empty">일치하는 명령 없음</li>
          ) : null}
        </ul>

        <div className="cmd-palette__footer">
          <span className="cmd-palette__footer-key">
            <kbd className="kbd">↑↓</kbd> 탐색
          </span>
          <span className="cmd-palette__footer-key">
            <kbd className="kbd">↵</kbd> 실행
          </span>
          <span className="cmd-palette__footer-key">
            <kbd className="kbd">Esc</kbd> 닫기
          </span>
        </div>
      </div>
    </div>
  );
}
