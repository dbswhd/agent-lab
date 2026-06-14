/** Parse `[human synthesis — 턴 요약]` system lines (Sprint C). */

const MARKER_RE = /^\[human synthesis[^\]]*\]\s*/i;
const LEAD_RE = /^리드:\s*(\S+)/im;
const HUMAN_SECTION_RE =
  /\*\*Human\*\*\s*([\s\S]*?)(?=\n\*\*에이전트|\n\*\*|$)/i;
const AGENTS_SECTION_RE = /\*\*에이전트\s*\(요약\)\*\*\s*([\s\S]*)/i;
const AGENT_BULLET_RE = /^-\s*\*\*([^*]+)\*\*:\s*(.+)$/gm;

export type HumanSynthesisAgentLine = {
  name: string;
  summary: string;
};

export type ParsedHumanSynthesis = {
  lead: string | null;
  humanExcerpt: string;
  agents: HumanSynthesisAgentLine[];
};

export function stripHumanSynthesisMarker(text: string): string {
  return text.replace(MARKER_RE, "").trim();
}

export function parseHumanSynthesisBody(raw: string): ParsedHumanSynthesis {
  let rest = stripHumanSynthesisMarker(raw);
  let lead: string | null = null;
  const leadMatch = LEAD_RE.exec(rest);
  if (leadMatch) {
    lead = leadMatch[1].trim().toLowerCase();
    rest = rest.slice(leadMatch.index! + leadMatch[0].length).trim();
  }

  const humanMatch = HUMAN_SECTION_RE.exec(rest);
  const agentsMatch = AGENTS_SECTION_RE.exec(rest);

  const humanExcerpt = (humanMatch?.[1] ?? "").trim();
  const agentsBlock = (agentsMatch?.[1] ?? "").trim();

  const agents: HumanSynthesisAgentLine[] = [];
  if (agentsBlock) {
    AGENT_BULLET_RE.lastIndex = 0;
    let m: RegExpExecArray | null;
    while ((m = AGENT_BULLET_RE.exec(agentsBlock)) !== null) {
      const name = m[1].trim();
      const summary = m[2].trim();
      if (name && summary && !summary.startsWith("(에이전트 응답 없음)")) {
        agents.push({ name, summary });
      }
    }
  }

  if (!humanExcerpt && !agents.length && rest.trim()) {
    return { lead, humanExcerpt: rest.trim(), agents: [] };
  }

  return { lead, humanExcerpt, agents };
}

export function isHumanSynthesisContent(content: string): boolean {
  return MARKER_RE.test((content || "").trimStart());
}

export function isHumanSynthesisLine(line: {
  role: string;
  content: string;
  visibility?: string;
}): boolean {
  const content = line.content || "";
  if (line.visibility === "human" && isHumanSynthesisContent(content)) {
    return true;
  }
  return line.role === "system" && isHumanSynthesisContent(content);
}
