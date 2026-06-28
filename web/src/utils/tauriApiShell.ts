import { invoke } from "@tauri-apps/api/core";

import { isTauri } from "../theme";

export type ApiShellStatus = {
  tauri_owns_api: boolean;
  skip_tauri_api: boolean;
  health_ok: boolean;
  sessions_dir_mismatch: boolean;
  expected_sessions_dir: string;
  remote_sessions_dir: string | null;
};

export async function fetchApiShellStatus(): Promise<ApiShellStatus | null> {
  if (!isTauri()) return null;
  try {
    return await invoke<ApiShellStatus>("api_shell_status");
  } catch {
    return null;
  }
}

export async function restartTauriApi(): Promise<
  { ok: true } | { ok: false; error: string }
> {
  if (!isTauri()) {
    return { ok: false, error: "not tauri" };
  }
  try {
    await invoke("api_restart");
    return { ok: true };
  } catch (err) {
    const message =
      err instanceof Error ? err.message : typeof err === "string" ? err : String(err);
    return { ok: false, error: message };
  }
}
