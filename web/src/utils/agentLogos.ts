/** Brand marks served from `web/public/icons/vendor/`. */
export const AGENT_LOGO_BY_ID: Record<string, string> = {
  cursor: "/icons/vendor/cursor.png",
  codex: "/icons/vendor/codex.png",
  claude: "/icons/vendor/claude.png",
  kimi: "/icons/vendor/kimi.png",
  kimi_work: "/icons/vendor/kimi-work.png",
};

export function agentLogoSrc(id: string): string | undefined {
  return AGENT_LOGO_BY_ID[id.toLowerCase()];
}

export function hasAgentLogo(id: string): boolean {
  return Boolean(agentLogoSrc(id));
}
