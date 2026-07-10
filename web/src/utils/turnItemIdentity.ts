type IdentifiedItem = {
  readonly id: string;
};

export function normalizeActivity(text: string): {
  readonly kind: "reasoning_summary" | "activity";
  readonly text: string;
} {
  const trimmed = text.trim();
  if (trimmed.startsWith("[thinking]")) {
    const body = trimmed.slice("[thinking]".length).trim();
    return { kind: "reasoning_summary", text: body || trimmed };
  }
  return { kind: "activity", text: trimmed };
}

export function toolFingerprint(tool: string, args?: string): string {
  return `${tool}|${(args ?? "").trim()}`;
}

export function uniqueTurnItemId(
  base: string,
  items: readonly IdentifiedItem[],
): string {
  const existingIds = new Set(items.map((item) => item.id));
  if (!existingIds.has(base)) return base;
  let suffix = 2;
  while (existingIds.has(`${base}-${suffix}`)) suffix += 1;
  return `${base}-${suffix}`;
}
