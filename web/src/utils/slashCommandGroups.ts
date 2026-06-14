import type { SlashCommandRecord } from "../api/client";

export type SlashCommandGroupKey =
  | "built_in"
  | "cursor"
  | "codex"
  | "claude"
  | "external";

export const SLASH_COMMAND_GROUP_ORDER: SlashCommandGroupKey[] = [
  "built_in",
  "cursor",
  "codex",
  "claude",
  "external",
];

export const SLASH_COMMAND_GROUP_LABELS: Record<SlashCommandGroupKey, string> =
  {
    built_in: "Built-in",
    cursor: "Cursor",
    codex: "Codex",
    claude: "Claude",
    external: "External",
  };

export function slashCommandGroupKey(
  cmd: SlashCommandRecord,
): SlashCommandGroupKey {
  if (cmd.scope === "external" || cmd.kind === "external") return "external";
  if (cmd.agent === "claude") return "claude";
  if (cmd.agent === "codex") return "codex";
  if (cmd.agent === "cursor") return "cursor";
  return "built_in";
}

export function groupSlashCommands(
  commands: SlashCommandRecord[],
): Record<SlashCommandGroupKey, SlashCommandRecord[]> {
  const groups: Record<SlashCommandGroupKey, SlashCommandRecord[]> = {
    built_in: [],
    cursor: [],
    codex: [],
    claude: [],
    external: [],
  };
  for (const cmd of commands) {
    groups[slashCommandGroupKey(cmd)].push(cmd);
  }
  for (const key of SLASH_COMMAND_GROUP_ORDER) {
    groups[key].sort((a, b) => a.slash.localeCompare(b.slash));
  }
  return groups;
}

/** Agent plugin groups default collapsed when list is long. */
export function defaultSlashGroupOpen(
  groups: Record<SlashCommandGroupKey, SlashCommandRecord[]>,
): Record<SlashCommandGroupKey, boolean> {
  return {
    built_in: true,
    external: true,
    cursor: groups.cursor.length <= 8,
    codex: groups.codex.length <= 8,
    claude: groups.claude.length <= 8,
  };
}
