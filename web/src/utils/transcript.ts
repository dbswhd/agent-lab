export type AgentRole =
  | "you"
  | "cursor"
  | "codex"
  | "claude"
  | "planner"
  | "critic"
  | "scribe"
  | "system";

export type ChatMessage = {
  id: string;
  role: AgentRole;
  label: string;
  body: string;
  sent?: boolean;
};

const LABELS: Record<string, string> = {
  you: "나",
  cursor: "Cursor",
  codex: "Codex",
  claude: "Claude",
  planner: "Planner",
  critic: "Critic",
  scribe: "Scribe",
  system: "시스템",
};

export function agentLabel(id: string): string {
  return LABELS[id] ?? id;
}

export function chatLineToMessage(line: {
  role: string;
  agent?: string | null;
  content: string;
}, i: number): ChatMessage {
  if (line.role === "user") {
    return {
      id: `u-${i}`,
      role: "you",
      label: "나",
      body: line.content,
      sent: true,
    };
  }
  if (line.role === "agent" && line.agent) {
    const role = line.agent as AgentRole;
    return {
      id: `a-${i}-${line.agent}`,
      role,
      label: agentLabel(line.agent),
      body: line.content,
      sent: false,
    };
  }
  return {
    id: `s-${i}`,
    role: "system",
    label: "시스템",
    body: line.content,
    sent: false,
  };
}

export function parseTranscript(md: string): ChatMessage[] {
  const messages: ChatMessage[] = [];
  const chunks = md.split(/^## /m).filter(Boolean);
  for (const chunk of chunks) {
    const nl = chunk.indexOf("\n");
    const heading = (nl >= 0 ? chunk.slice(0, nl) : chunk).trim();
    const body = (nl >= 0 ? chunk.slice(nl + 1) : "").trim();
    if (!body || heading.toLowerCase().includes("session transcript")) continue;
    const key = heading.toLowerCase();
    let role: AgentRole = "system";
    if (key === "human") role = "you";
    else if (key === "planner") role = "planner";
    else if (key === "critic") role = "critic";
    else if (key === "scribe") role = "scribe";
    else if (key === "cursor") role = "cursor";
    else if (key === "codex") role = "codex";
    else if (key === "claude") role = "claude";
    messages.push({
      id: heading,
      role,
      label: heading,
      body,
      sent: role === "you",
    });
  }
  return messages;
}

export function topicAsUserMessage(topic: string): ChatMessage {
  return {
    id: "topic",
    role: "you",
    label: "나",
    body: topic,
    sent: true,
  };
}
