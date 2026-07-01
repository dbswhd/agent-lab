export type AgentMentionRow = {
  id: string;
  label: string;
};

/** Filter active roster agents for ``@`` autocomplete. */
export function filterAgentMentions(
  query: string,
  agents: readonly AgentMentionRow[],
): AgentMentionRow[] {
  const q = query.trim().toLowerCase();
  if (!q) return [...agents];
  return agents.filter((agent) => {
    const id = agent.id.toLowerCase();
    const label = agent.label.toLowerCase();
    return id.includes(q) || label.includes(q) || id.replace(/_/g, "-").includes(q);
  });
}

/** True when ``@`` query looks like a file path, not an agent handle. */
export function mentionQueryLooksLikePath(query: string): boolean {
  return query.includes("/") || query.includes(".");
}
