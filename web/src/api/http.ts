import { isTauri } from "@tauri-apps/api/core";
import { parseApiErrorDetail } from "../utils/apiError";

const API_ORIGIN = "http://127.0.0.1:8765";

export function apiBase(): string {
  const fromEnv = import.meta.env.VITE_API_BASE as string | undefined;
  if (fromEnv) return fromEnv.replace(/\/$/, "");
  if (typeof window !== "undefined") {
    const port = window.location.port;
    if (port === "1420" || port === "5173" || port === "8765") {
      return "";
    }
  }
  if (isTauri()) return API_ORIGIN;
  return "";
}

export function apiUrl(path: string): string {
  const base = apiBase();
  return base ? `${base}${path}` : path;
}

export async function apiJson<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(apiUrl(path), init);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(parseApiErrorDetail(text) || res.statusText);
  }
  return res.json() as Promise<T>;
}
