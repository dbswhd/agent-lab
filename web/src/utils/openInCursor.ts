/** Open workspace in the Cursor app (escape hatch — not an Agent Lab failure). */

export function cursorFileUri(workspacePath: string): string {
  const trimmed = workspacePath.trim();
  if (!trimmed) return "";
  // cursor://file/<absolute-path> opens the folder/file in Cursor Desktop.
  const normalized = trimmed.replace(/\\/g, "/");
  const path = normalized.startsWith("/") ? normalized : `/${normalized}`;
  return `cursor://file${path}`;
}

export async function openWorkspaceInCursor(
  workspacePath: string | null | undefined,
): Promise<{ ok: true } | { ok: false; reason: string }> {
  const path = workspacePath?.trim() ?? "";
  if (!path) {
    return { ok: false, reason: "workspace_missing" };
  }
  const uri = cursorFileUri(path);
  try {
    const { openUrl } = await import("@tauri-apps/plugin-opener");
    await openUrl(uri);
    return { ok: true };
  } catch {
    // Browser / non-Tauri: try navigating; OS may hand off to Cursor.
    try {
      window.open(uri, "_blank", "noopener,noreferrer");
      return { ok: true };
    } catch {
      return { ok: false, reason: "open_failed" };
    }
  }
}
