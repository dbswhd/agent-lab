import {
  isHumanSynthesisLine,
  stripHumanSynthesisMarker,
} from "./humanSynthesis";

export type AgentRole =
  | "you"
  | "cursor"
  | "codex"
  | "claude"
  | "planner"
  | "critic"
  | "scribe"
  | "system";

export type AgentEnvelope = {
  act: string;
  refs?: string[];
  confidence?: number;
  anchor_id?: string;
};

export type ChatMessage = {
  id: string;
  role: AgentRole;
  label: string;
  body: string;
  sent?: boolean;
  parallelRound?: number;
  /** Peer coordination channel — hidden unless “동료 채널” is on. */
  peerChannel?: boolean;
  /** Human-facing turn summary (Sprint C). */
  humanSynthesis?: boolean;
  envelope?: AgentEnvelope;
  /** R2+ reply had ```agent-envelope``` fence but JSON failed to parse */
  envelopeParseError?: boolean;
  /** 0-based index in chat.jsonl */
  chatLineIndex?: number;
  /** When set, renders a round topology divider before this message */
  roundDivider?: number;
  /** Live Cursor-style activity lines while the agent is running */
  activities?: string[];
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

function isPeerLine(line: {
  role: string;
  content: string;
  visibility?: string;
}): boolean {
  if (line.visibility === "peer") return true;
  if (line.role === "agent" && /^\[이번 턴\s*·\s*동료 발화\]/i.test(line.content.trim())) {
    return true;
  }
  if (
    line.role === "system" &&
    /peer digest/i.test(line.content)
  ) {
    return true;
  }
  return false;
}

export function chatLineToMessage(
  line: {
    role: string;
    agent?: string | null;
    content: string;
    parallel_round?: number;
    visibility?: string;
    envelope?: AgentEnvelope;
  },
  i: number,
): ChatMessage {
  const peerChannel = isPeerLine(line);
  const humanSynthesis = isHumanSynthesisLine(line);
  if (line.role === "user") {
    return {
      id: `u-${i}`,
      role: "you",
      label: "나",
      body: line.content,
      sent: true,
      chatLineIndex: i,
      peerChannel: false,
      humanSynthesis: false,
    };
  }
  if (line.role === "agent" && line.agent) {
    const role = line.agent as AgentRole;
    const r = line.parallel_round ?? 1;
    return {
      id: `a-${i}-${line.agent}-r${r}`,
      role,
      label: agentLabel(line.agent),
      body: line.content,
      sent: false,
      parallelRound: r,
      chatLineIndex: i,
      peerChannel,
      humanSynthesis: false,
      envelope: line.envelope,
    };
  }
  return {
    id: `s-${i}`,
    role: "system",
    label: humanSynthesis ? "턴 요약" : peerChannel ? "동료 채널" : "시스템",
    body: humanSynthesis
      ? stripHumanSynthesisMarker(line.content)
      : line.content,
    sent: false,
    chatLineIndex: i,
    peerChannel,
    humanSynthesis,
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
