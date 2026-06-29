import {
  isHumanSynthesisLine,
  stripHumanSynthesisMarker,
} from "./humanSynthesis";
import type { TurnItem } from "./turnItems";

export type TranscriptActivityMarker = {
  id: string;
  tier: "P0" | "P1" | "P2" | "P3";
  title: string;
  body?: string;
  kind: string;
  createdAt: number;
  read: boolean;
};

export type AgentRole =
  | "you"
  | "cursor"
  | "codex"
  | "claude"
  | "kimi"
  | "kimi_work"
  | "local"
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
  /** Session activity / notification marker (P0–P3) inline in transcript */
  activityMarker?: TranscriptActivityMarker;
  turnItems?: TurnItem[];
  /** Files sent with this user message (shown above bubble, not in composer). */
  attachments?: string[];
};

const LABELS: Record<string, string> = {
  you: "나",
  cursor: "Cursor",
  codex: "Codex",
  claude: "Claude",
  kimi: "KIMI",
  kimi_work: "Kimi Work",
  local: "Local",
  planner: "Planner",
  critic: "Critic",
  scribe: "Scribe",
  system: "시스템",
};

export function agentLabel(id: string): string {
  return LABELS[id] ?? id;
}

/** Split legacy `[첨부] …` user lines into attachment chips + visible body. */
export function parseUserMessageContent(content: string): {
  body: string;
  attachments?: string[];
} {
  const trimmed = content.trim();
  const attachOnly = /^\[첨부\]\s*(.+)$/s.exec(trimmed);
  if (!attachOnly) return { body: content };

  const payload = attachOnly[1].trim();
  const multi = /^(\d+)개 파일$/.exec(payload);
  if (multi) {
    return { body: "", attachments: [`${multi[1]}개 파일`] };
  }
  return { body: "", attachments: [payload] };
}

function isPeerLine(line: {
  role: string;
  content: string;
  visibility?: string;
}): boolean {
  if (line.visibility === "peer") return true;
  if (
    line.role === "agent" &&
    /^\[이번 턴\s*·\s*동료 발화\]/i.test(line.content.trim())
  ) {
    return true;
  }
  if (line.role === "system" && /peer digest/i.test(line.content)) {
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
    const parsed = parseUserMessageContent(line.content);
    return {
      id: `u-${i}`,
      role: "you",
      label: "나",
      body: parsed.body,
      attachments: parsed.attachments,
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
    else if (key === "kimi" || key === "kimi work") role = "kimi";
    else if (key === "kimi_work") role = "kimi_work";
    else if (key === "local") role = "local";
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

export function topicAsUserMessage(
  topic: string,
  attachments?: string[],
): ChatMessage {
  return {
    id: "topic",
    role: "you",
    label: "나",
    body: topic,
    attachments: attachments?.length ? attachments : undefined,
    sent: true,
  };
}

const REPLY_WAIT_ROLES = new Set<AgentRole>([
  "cursor",
  "codex",
  "claude",
  "kimi",
  "kimi_work",
  "local",
  "planner",
  "critic",
  "scribe",
]);

/** Agent roles that show a "reply in progress" waiting bubble. */
export function isReplyWaitRole(role: AgentRole): boolean {
  return REPLY_WAIT_ROLES.has(role);
}
