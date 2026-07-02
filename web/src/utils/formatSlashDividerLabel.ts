/** Format slash summaries for round-divider transcript lines. */
export type SlashDividerParts = {
  command: string;
  message: string;
};

export function parseSlashDividerParts(text: string): SlashDividerParts | null {
  const trimmed = text.trim();
  if (!trimmed) return null;

  const body = trimmed.startsWith("[slash]")
    ? trimmed.slice("[slash]".length).trim()
    : trimmed;

  const colonIdx = body.indexOf(":");
  if (colonIdx <= 0 || !body.startsWith("/")) return null;

  const command = body.slice(0, colonIdx).trim();
  const message = body.slice(colonIdx + 1).trim();
  if (!command || !message) return null;

  return { command, message };
}

export function formatSlashDividerLabel(text: string): string {
  const trimmed = text.trim();
  if (!trimmed) return trimmed;

  const parts = parseSlashDividerParts(trimmed);
  if (parts) return `${parts.command} · ${parts.message}`;

  return trimmed.startsWith("[slash]")
    ? trimmed.slice("[slash]".length).trim()
    : trimmed;
}
