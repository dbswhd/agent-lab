import type { SlashCommandRecord } from "../api/client";

/** Wire keyboard navigation into the composer's onKeyDown handler. */
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
