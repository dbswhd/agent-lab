import { apiBase } from "./http";

/** WebSocket URL for the PTY terminal of a session. */
export function terminalWsUrl(sessionId: string): string {
  const base = apiBase();
  const wsBase = base
    ? base.replace(/^https?/, (p) => (p === "https" ? "wss" : "ws"))
    : `${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.host}`;
  return `${wsBase}/api/sessions/${encodeURIComponent(sessionId)}/terminal`;
}

export function authRunWsUrl(runId: string): string {
  const base = apiBase();
  const wsBase = base
    ? base.replace(/^https?/, (protocol) =>
        protocol === "https" ? "wss" : "ws",
      )
    : `${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.host}`;
  return `${wsBase}/api/auth/runs/${encodeURIComponent(runId)}`;
}
