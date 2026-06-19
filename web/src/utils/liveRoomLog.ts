import type { LiveMsg } from "../run/runSessionRegistry";

export type LiveRoomEvent = Record<string, unknown> & { type?: string };

/** Drop back-to-back repeated paragraphs and exact halved duplicates. */
export function dedupeAdjacentStreamDupes(text: string): string {
  const t = text.trim();
  if (!t) return text;
  const half = Math.floor(t.length / 2);
  if (t.length % 2 === 0 && half > 0 && t.slice(0, half) === t.slice(half)) {
    return t.slice(0, half);
  }
  const parts = t.split(/\n{2,}/);
  if (parts.length < 2) return t;
  const out: string[] = [];
  for (const part of parts) {
    const chunk = part.trim();
    if (!chunk) continue;
    if (out.length && out[out.length - 1]!.trim() === chunk) continue;
    out.push(part);
  }
  return out.join("\n\n");
}
export function mergeAgentReplyBody(
  streamed: string,
  finalBody: string,
): string {
  const streamedClean = dedupeAdjacentStreamDupes(streamed);
  const finalClean = dedupeAdjacentStreamDupes(finalBody);
  if (!streamedClean.trim()) return finalClean || finalBody || "(empty)";
  if (!finalClean.trim()) return streamedClean;
  if (finalClean.startsWith(streamedClean)) return finalClean;
  if (
    streamedClean.startsWith(finalClean) &&
    streamedClean.length > finalClean.length + 40
  ) {
    return streamedClean;
  }
  if (finalClean.length < Math.max(200, Math.floor(streamedClean.length / 8))) {
    return streamedClean;
  }
  return finalClean.length >= streamedClean.length ? finalClean : streamedClean;
}

export function replayLiveLogToMessages(
  events: LiveRoomEvent[],
  labelFor: (agentId: string) => string,
): LiveMsg[] {
  const out: LiveMsg[] = [];
  const typing = new Map<string, LiveMsg>();

  const tid = (agent: string, round: number) => `typing-${agent}-r${round}`;

  for (const ev of events) {
    const t = String(ev.type ?? "");
    const aid = ev.agent != null ? String(ev.agent) : "";
    const round = Number(ev.round ?? 1);

    if (t === "agent_start" && aid) {
      const id = tid(aid, round);
      const msg: LiveMsg = {
        id,
        role: aid as LiveMsg["role"],
        label: labelFor(aid),
        body: "",
        typing: true,
        parallelRound: round,
        activities: [],
        toolCards: [],
      };
      typing.set(id, msg);
      out.push(msg);
      continue;
    }

    if (!aid) continue;
    const id = tid(aid, round);
    let msg = typing.get(id);
    if (!msg) {
      msg = {
        id,
        role: aid as LiveMsg["role"],
        label: labelFor(aid),
        body: "",
        typing: true,
        parallelRound: round,
        activities: [],
        toolCards: [],
      };
      typing.set(id, msg);
      out.push(msg);
    }

    if (t === "agent_token" && typeof ev.text === "string") {
      msg.body = `${msg.body ?? ""}${String(ev.text)}`;
      continue;
    }

    if (t === "agent_activity" && typeof ev.text === "string") {
      const line = String(ev.text);
      const prev = msg.activities ?? [];
      msg.activities =
        prev[prev.length - 1] === line ? prev : [...prev, line].slice(-12);
      continue;
    }

    if (t === "tool_start") {
      const tool = String(ev.tool ?? "tool");
      const argsObj = ev.args as Record<string, unknown> | undefined;
      const target = typeof argsObj?.target === "string" ? argsObj.target : "";
      const cards = [...(msg.toolCards ?? [])];
      cards.push({
        id: `tool-${tool}-${cards.length}`,
        tool,
        args: target || undefined,
        startedAt: Date.now(),
      });
      msg.toolCards = cards.slice(-16);
      continue;
    }

    if (t === "tool_output" && typeof ev.chunk === "string" && ev.chunk) {
      const tool = String(ev.tool ?? "tool");
      const chunk = String(ev.chunk);
      const cards = [...(msg.toolCards ?? [])];
      for (let i = cards.length - 1; i >= 0; i -= 1) {
        if (cards[i].tool === tool && !cards[i].doneAt) {
          cards[i] = {
            ...cards[i],
            output: `${cards[i].output ?? ""}${chunk}`.slice(-4000),
          };
          break;
        }
      }
      msg.toolCards = cards;
      continue;
    }

    if (t === "tool_done") {
      const tool = String(ev.tool ?? "tool");
      const cards = [...(msg.toolCards ?? [])];
      for (let i = cards.length - 1; i >= 0; i -= 1) {
        if (cards[i].tool === tool && !cards[i].doneAt) {
          cards[i] = { ...cards[i], doneAt: Date.now() };
          break;
        }
      }
      msg.toolCards = cards;
      continue;
    }

    if (t === "agent_done") {
      const finalId = `msg-${aid}-r${round}-live`;
      const body = mergeAgentReplyBody(
        msg.body ?? "",
        typeof ev.content === "string" ? ev.content : "",
      );
      const idx = out.findIndex((m) => m.id === id);
      const finalized: LiveMsg = {
        ...msg,
        id: finalId,
        typing: false,
        body,
        envelope: ev.envelope as LiveMsg["envelope"],
        envelopeParseError: ev.envelope_parse_error === true,
      };
      if (idx >= 0) out[idx] = finalized;
      typing.delete(id);
      continue;
    }

    if (t === "agent_error") {
      const note = typeof ev.note === "string" ? ev.note : "";
      const errMsg = typeof ev.message === "string" ? ev.message : "";
      const partial = (msg.body ?? "").trim();
      const body =
        partial && errMsg
          ? `${partial}\n\n—\n[오류] ${errMsg}`
          : note || errMsg || partial || "agent error";
      const idx = out.findIndex((m) => m.id === id);
      const finalized: LiveMsg = {
        ...msg,
        id: `err-${aid}-r${round}-live`,
        typing: false,
        body,
      };
      if (idx >= 0) out[idx] = finalized;
      typing.delete(id);
    }
  }

  return out;
}
