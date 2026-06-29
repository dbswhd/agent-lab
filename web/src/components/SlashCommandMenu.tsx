import { useEffect, useMemo, useRef, useState, type RefObject } from "react";
import type { SlashCommandRecord } from "../api/client";
import { useDismissOnPointerDownOutside } from "../hooks/useDismissOnPointerDownOutside";
import {
  buildSlashMenuSections,
  defaultSlashMenuExpanded,
  filterSlashCommands,
  flattenSlashMenuSections,
  groupSlashMenuCommands,
  SLASH_MENU_GROUP_LABELS,
  slashMenuDisplayName,
  type SlashMenuGroupKey,
} from "../utils/slashCommandMenuGroups";

type Props = {
  value: string;
  commands: SlashCommandRecord[];
  onSelect: (slash: string) => void;
  onDismiss?: () => void;
  /** Clicks inside this region (composer capsule) do not dismiss the menu. */
  insideRef?: RefObject<Node | null>;
  disabled?: boolean;
  highlightedIndex?: number;
  onHighlightChange?: (index: number) => void;
  onVisibleCommandsChange?: (commands: SlashCommandRecord[]) => void;
};

export function SlashCommandMenu({
  value,
  commands,
  onSelect,
  onDismiss,
  insideRef,
  disabled,
  highlightedIndex,
  onHighlightChange,
  onVisibleCommandsChange,
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

  const filteredGroups = useMemo(() => {
    const filtered = filterSlashCommands(commands, query);
    return groupSlashMenuCommands(filtered);
  }, [commands, query]);

  const [expanded, setExpanded] = useState<Record<SlashMenuGroupKey, boolean>>(
    () => defaultSlashMenuExpanded(filteredGroups),
  );
  const wasOpenRef = useRef(false);

  useEffect(() => {
    if (open && !wasOpenRef.current) {
      setExpanded(defaultSlashMenuExpanded(filteredGroups));
    }
    wasOpenRef.current = open;
  }, [open, filteredGroups]);

  const sections = useMemo(
    () => buildSlashMenuSections(commands, query, expanded),
    [commands, query, expanded],
  );

  const visibleCommands = useMemo(
    () => flattenSlashMenuSections(sections),
    [sections],
  );

  useEffect(() => {
    if (!open) return;
    onVisibleCommandsChange?.(visibleCommands);
  }, [open, onVisibleCommandsChange, visibleCommands]);

  const active = visibleCommands[hi] ?? visibleCommands[0] ?? null;
  let flatIndex = 0;

  if (!open) return null;

  return (
    <div
      className="slash-command-menu"
      ref={menuRef}
      data-testid="slash-command-menu"
      role="listbox"
      aria-label="slash commands"
    >
      <div className="slash-command-menu__main">
        <div className="slash-command-menu__scroll">
          {sections.map((section) => (
            <section
              key={section.key}
              className="slash-command-menu__section"
              aria-label={SLASH_MENU_GROUP_LABELS[section.key]}
            >
              <header className="slash-command-menu__section-label">
                {SLASH_MENU_GROUP_LABELS[section.key]}
              </header>
              <ul className="slash-command-menu__list">
                {section.items.map((cmd) => {
                  const index = flatIndex;
                  flatIndex += 1;
                  return (
                    <li key={cmd.id}>
                      <button
                        type="button"
                        className={[
                          "slash-command-menu__item",
                          index === hi ? "is-active" : "",
                          cmd.enabled === false ? "is-disabled" : "",
                        ]
                          .filter(Boolean)
                          .join(" ")}
                        role="option"
                        aria-selected={index === hi}
                        disabled={cmd.enabled === false}
                        onMouseEnter={() => onHighlightChange?.(index)}
                        onMouseDown={(event) => event.preventDefault()}
                        onClick={() => {
                          if (cmd.enabled === false) return;
                          onSelect(cmd.slash);
                        }}
                      >
                        <span className="slash-command-menu__name">
                          {slashMenuDisplayName(cmd)}
                        </span>
                      </button>
                    </li>
                  );
                })}
              </ul>
              {section.hiddenCount > 0 ? (
                <button
                  type="button"
                  className="slash-command-menu__more"
                  onMouseDown={(event) => event.preventDefault()}
                  onClick={() =>
                    setExpanded((prev) => ({ ...prev, [section.key]: true }))
                  }
                >
                  Show {section.hiddenCount} more
                </button>
              ) : null}
            </section>
          ))}
          {visibleCommands.length === 0 ? (
            <p className="slash-command-menu__empty">일치하는 명령 없음</p>
          ) : null}
        </div>
      </div>
      {active ? (
        <aside className="slash-command-menu__aside" aria-live="polite">
          <h3 className="slash-command-menu__aside-title">{active.label}</h3>
          <p className="slash-command-menu__aside-desc">
            {active.description ?? active.label}
          </p>
          {active.enabled === false ? (
            <p className="slash-command-menu__aside-meta">
              {active.disabled_reason ?? "현재 세션에서 사용할 수 없음"}
            </p>
          ) : null}
        </aside>
      ) : null}
    </div>
  );
}
