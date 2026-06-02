export const MIN_AGENT_ROUNDS = 1;
export const MAX_AGENT_ROUNDS = 4;
export const DEFAULT_AGENT_ROUNDS = 1;

const STORAGE_KEY = "agent-lab-agent-rounds";

export function getAgentRounds(): number {
  const stored = localStorage.getItem(STORAGE_KEY);
  if (stored == null) return DEFAULT_AGENT_ROUNDS;
  const n = Number.parseInt(stored, 10);
  if (!Number.isFinite(n)) return DEFAULT_AGENT_ROUNDS;
  return Math.max(MIN_AGENT_ROUNDS, Math.min(MAX_AGENT_ROUNDS, n));
}

export function setAgentRounds(rounds: number): void {
  const clamped = Math.max(
    MIN_AGENT_ROUNDS,
    Math.min(MAX_AGENT_ROUNDS, Math.round(rounds)),
  );
  localStorage.setItem(STORAGE_KEY, String(clamped));
}
