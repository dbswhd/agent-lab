/** Client-side mirror of ``agent_lab.room.agent_mentions`` for pending UI. */

const MENTION_RE = /(?<![A-Za-z0-9_-])@([a-zA-Z][a-zA-Z0-9_-]*)\b/g;

const ALIASES: Record<string, string> = {
  "kimi-work": "kimi_work",
};

function canonicalMention(raw: string, active: Set<string>): string | null {
  let token = raw.trim().toLowerCase().replace(/^@/, "");
  if (!token) return null;
  token = ALIASES[token] ?? token;
  if (token === "kimi") {
    if (active.has("kimi_work")) return "kimi_work";
    if (active.has("kimi")) return "kimi";
    return null;
  }
  return active.has(token) ? token : null;
}

export function parseAgentMentions(text: string, activePool: string[]): string[] {
  const active = new Set(
    activePool.map((a) => a.trim().toLowerCase()).filter(Boolean),
  );
  const seen: string[] = [];
  for (const match of text.matchAll(MENTION_RE)) {
    const raw = match[1] ?? "";
    const canon = canonicalMention(raw, active);
    if (canon && !seen.includes(canon)) seen.push(canon);
  }
  return seen;
}

/** Roster the server will invoke after @-mention filtering. */
export function effectiveTurnAgents(body: string, rosterPool: string[]): string[] {
  const pool = rosterPool.map((a) => a.trim().toLowerCase()).filter(Boolean);
  if (!pool.length) return rosterPool;
  const mentions = parseAgentMentions(body, pool);
  if (!mentions.length) return rosterPool;
  const mentionSet = new Set(mentions);
  const filtered: string[] = [];
  const seen = new Set<string>();
  for (const raw of rosterPool) {
    const aid = raw.trim().toLowerCase();
    if (!aid || !mentionSet.has(aid) || seen.has(aid)) continue;
    seen.add(aid);
    filtered.push(aid);
  }
  return filtered.length ? filtered : rosterPool;
}
