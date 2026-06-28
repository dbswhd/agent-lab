const prefs = new Map<string, boolean>();

export function getDraftOpenPref(messageId: string): boolean | undefined {
  return prefs.get(messageId);
}

export function setDraftOpenPref(messageId: string, open: boolean): void {
  prefs.set(messageId, open);
}

/** Last agent reply id per role (for default-open Draft response). */
export function latestDraftMessageIdsByAgent(
  messages: readonly { id: string; role: string; body?: string; typing?: boolean }[],
  isAgentRole: (role: string) => boolean,
  hasDraftBody: (body: string | undefined) => boolean,
): Set<string> {
  const latest = new Map<string, string>();
  for (const message of messages) {
    if (!isAgentRole(message.role) || message.typing) continue;
    if (!hasDraftBody(message.body)) continue;
    latest.set(message.role, message.id);
  }
  return new Set(latest.values());
}
