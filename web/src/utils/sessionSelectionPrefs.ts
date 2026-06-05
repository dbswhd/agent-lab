const STORAGE_KEY = "agent-lab-last-session-id";

export function getLastSessionId(): string | null {
  const stored = localStorage.getItem(STORAGE_KEY);
  if (!stored) return null;
  const trimmed = stored.trim();
  return trimmed.length > 0 ? trimmed : null;
}

export function setLastSessionId(sessionId: string): void {
  localStorage.setItem(STORAGE_KEY, sessionId);
}

export function clearLastSessionId(): void {
  localStorage.removeItem(STORAGE_KEY);
}
