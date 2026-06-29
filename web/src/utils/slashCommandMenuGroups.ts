import type { SlashCommandRecord } from "../api/client";

export type SlashMenuGroupKey = "skills" | "commands" | "modes";

export const SLASH_MENU_GROUP_ORDER: SlashMenuGroupKey[] = [
  "skills",
  "commands",
  "modes",
];

export const SLASH_MENU_GROUP_LABELS: Record<SlashMenuGroupKey, string> = {
  skills: "Skills",
  commands: "Commands",
  modes: "Modes",
};

const MODE_SLASHES = new Set(["/plan", "/clarify", "/pipeline"]);

export const SLASH_MENU_VISIBLE_CAP = 3;

export function slashMenuDisplayName(cmd: SlashCommandRecord): string {
  const raw = cmd.slash.startsWith("/") ? cmd.slash.slice(1) : cmd.slash;
  return raw || cmd.label;
}

export function slashMenuGroupKey(cmd: SlashCommandRecord): SlashMenuGroupKey {
  const slash = cmd.slash.toLowerCase();
  if (MODE_SLASHES.has(slash)) return "modes";
  if (cmd.kind === "agent_invoke" || cmd.source === "skill") return "skills";
  return "commands";
}

export function filterSlashCommands(
  commands: SlashCommandRecord[],
  query: string,
): SlashCommandRecord[] {
  const rows = commands.filter((c) => c.enabled !== false);
  if (!query) return rows;
  const q = query.toLowerCase();
  return rows.filter(
    (c) =>
      c.slash.toLowerCase().includes(q) ||
      c.label.toLowerCase().includes(q) ||
      (c.description ?? "").toLowerCase().includes(q),
  );
}

export function groupSlashMenuCommands(
  commands: SlashCommandRecord[],
): Record<SlashMenuGroupKey, SlashCommandRecord[]> {
  const groups: Record<SlashMenuGroupKey, SlashCommandRecord[]> = {
    skills: [],
    commands: [],
    modes: [],
  };
  for (const cmd of commands) {
    groups[slashMenuGroupKey(cmd)].push(cmd);
  }
  for (const key of SLASH_MENU_GROUP_ORDER) {
    groups[key].sort((a, b) =>
      slashMenuDisplayName(a).localeCompare(slashMenuDisplayName(b)),
    );
  }
  return groups;
}

export type SlashMenuSection = {
  key: SlashMenuGroupKey;
  items: SlashCommandRecord[];
  hiddenCount: number;
};

export function buildSlashMenuSections(
  commands: SlashCommandRecord[],
  query: string,
  expanded: Record<SlashMenuGroupKey, boolean>,
  cap = SLASH_MENU_VISIBLE_CAP,
): SlashMenuSection[] {
  const filtered = filterSlashCommands(commands, query);
  const groups = groupSlashMenuCommands(filtered);
  const isFiltering = query.length > 0;

  return SLASH_MENU_GROUP_ORDER.flatMap((key) => {
    const rows = groups[key];
    if (rows.length === 0) return [];
    const showAll = isFiltering || expanded[key];
    const visible = showAll ? rows : rows.slice(0, cap);
    const hiddenCount = showAll ? 0 : Math.max(0, rows.length - visible.length);
    return [{ key, items: visible, hiddenCount }];
  });
}

export function flattenSlashMenuSections(
  sections: SlashMenuSection[],
): SlashCommandRecord[] {
  return sections.flatMap((section) => section.items);
}

export function defaultSlashMenuExpanded(
  groups: Record<SlashMenuGroupKey, SlashCommandRecord[]>,
): Record<SlashMenuGroupKey, boolean> {
  return {
    skills: groups.skills.length <= SLASH_MENU_VISIBLE_CAP,
    commands: groups.commands.length <= SLASH_MENU_VISIBLE_CAP,
    modes: true,
  };
}
