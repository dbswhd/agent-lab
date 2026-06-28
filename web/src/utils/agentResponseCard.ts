import type { ChatMessage } from "./transcript";
import { actLabel, normalizeAct } from "./agentEnvelope";

const ENVELOPE_FENCE = /^\s*```agent-envelope\s*\n[\s\S]*?\n```\s*/i;
const PROPOSED_RE = /\[PROPOSED:\s*([^\]]+)\]/gi;

export function stripAgentReplyBody(body: string): string {
  return body.replace(ENVELOPE_FENCE, "").trim();
}

export type AgentResponseCardFields = {
  status: string;
  summary?: string;
  evidence: string[];
  decisionsNeeded: string[];
  nextActions: string[];
};

function stripEnvelopeFence(body: string): string {
  return stripAgentReplyBody(body);
}

function firstParagraph(text: string): string {
  const para = text.split(/\n\s*\n/)[0]?.trim() ?? text.trim();
  return para.length > 320 ? `${para.slice(0, 317)}…` : para;
}

function statusFromAct(act: string | undefined): string {
  const normalized = normalizeAct(act);
  if (!normalized) return "reply";
  switch (normalized) {
    case "BLOCK":
      return "blocked";
    case "CHALLENGE":
      return "review_needed";
    case "ENDORSE":
      return "endorsed";
    case "PROPOSE":
      return "proposed";
    case "AMEND":
      return "amended";
    case "PASS":
      return "pass";
    default:
      return String(normalized).toLowerCase();
  }
}

function statusLabel(status: string, act: string | undefined): string {
  if (act) return actLabel(act);
  const labels: Record<string, string> = {
    blocked: "Blocked",
    review_needed: "Review needed",
    endorsed: "Endorsed",
    proposed: "Proposed",
    amended: "Amended",
    pass: "Pass",
    reply: "Reply",
  };
  return labels[status] ?? status;
}

export function buildAgentResponseCard(
  message: ChatMessage & { typing?: boolean },
): AgentResponseCardFields | null {
  if (message.typing || message.humanSynthesis || message.peerChannel) {
    return null;
  }
  if (
    message.role !== "cursor" &&
    message.role !== "codex" &&
    message.role !== "claude" &&
    message.role !== "planner" &&
    message.role !== "critic" &&
    message.role !== "scribe"
  ) {
    return null;
  }

  const envelope = message.envelope;
  const act = envelope?.act;
  const bodyText = stripEnvelopeFence(message.body);
  const envelopeMessage =
    typeof (envelope as { message?: string } | undefined)?.message === "string"
      ? String((envelope as { message?: string }).message).trim()
      : "";

  const status = statusFromAct(act);
  const summary =
    envelopeMessage ||
    (bodyText && !bodyText.startsWith("```") ? firstParagraph(bodyText) : "");

  const evidence = [...(envelope?.refs ?? [])].filter(Boolean);
  const decisionsNeeded: string[] = [];
  if (normalizeAct(act) === "BLOCK" || normalizeAct(act) === "CHALLENGE") {
    if (evidence.length) decisionsNeeded.push(...evidence);
    else if (summary) decisionsNeeded.push(summary);
  }

  const nextActions: string[] = [];
  if (bodyText) {
    for (const match of bodyText.matchAll(PROPOSED_RE)) {
      const title = match[1]?.trim();
      if (title) nextActions.push(title);
    }
  }
  if (
    (normalizeAct(act) === "PROPOSE" || normalizeAct(act) === "AMEND") &&
    nextActions.length === 0 &&
    summary
  ) {
    nextActions.push(summary);
  }

  if (!envelope?.act && !summary && evidence.length === 0) {
    return null;
  }

  return {
    status: statusLabel(status, act),
    summary: summary || undefined,
    evidence,
    decisionsNeeded,
    nextActions,
  };
}
