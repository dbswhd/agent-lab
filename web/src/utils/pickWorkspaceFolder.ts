import { isTauri } from "@tauri-apps/api/core";
import { pickFolderViaDesktopApi } from "../api/client";

export async function pickWorkspaceFolder(
  defaultPath?: string | null,
): Promise<string | null> {
  if (isTauri()) {
    const { open } = await import("@tauri-apps/plugin-dialog");
    const selected = await open({
      directory: true,
      multiple: false,
      defaultPath: defaultPath ?? undefined,
      title: "작업 폴더 선택",
    });
    if (selected == null) return null;
    return typeof selected === "string" ? selected : null;
  }

  try {
    const res = await pickFolderViaDesktopApi(defaultPath);
    if (res.available) {
      return res.path;
    }
  } catch {
    /* API offline or proxy missing — fall back to manual entry */
  }

  const hint = defaultPath ? `\n(예: ${defaultPath})` : "";
  const raw = window.prompt(`작업 폴더 경로를 입력하세요.${hint}`);
  const trimmed = raw?.trim();
  return trimmed || null;
}
