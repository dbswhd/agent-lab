import type { SessionDetail } from "../api/client";
import { replayLiveLogToMessages } from "./liveRoomLog";
import { mergePersistedChatWithLiveLog } from "./sessionChatMerge";
import {
  agentLabel,
  chatLineToMessage,
  parseTranscript,
  topicAsUserMessage,
} from "./transcript";
import { roundDividerLabel } from "./roundTopology";
import type { LiveMsg } from "../run/runSessionRegistry";

export function chatFingerprint(session: SessionDetail): string {
  const chat = session.chat;
  if (!chat?.length) {
    return `${session.id}:t:${session.transcript_md?.length ?? 0}:${session.topic}`;
  }
  const last = chat[chat.length - 1];
  return `${session.id}:${chat.length}:${last.ts ?? ""}:${last.content.length}`;
}

export function attachmentSendTopic(
  fileNames: { file: { name: string } }[],
): string {
  if (fileNames.length === 1) return `[첨부] ${fileNames[0]!.file.name}`;
  return `[첨부] ${fileNames.length}개 파일`;
}

export function sessionToMessages(
  session: SessionDetail,
  reviewModeHint = false,
): LiveMsg[] {
  let out: LiveMsg[];
  if (session.chat && session.chat.length > 0) {
    out = [];
    let lastRound = 0;
    for (let i = 0; i < session.chat.length; i++) {
      const line = session.chat[i];
      if (line.role === "user") {
        lastRound = 0;
      }
      const pr = line.parallel_round ?? (line.role === "agent" ? 1 : 0);
      if (line.role === "agent" && pr >= 1 && pr !== lastRound) {
        out.push({
          id: `round-divider-${i}-${pr}`,
          role: "system",
          label: "",
          body: roundDividerLabel(pr, reviewModeHint),
          roundDivider: pr,
        });
        lastRound = pr;
      }
      out.push(chatLineToMessage(line, i));
    }
  } else if (session.live_log && session.live_log.length > 0) {
    const persisted =
      session.chat_total != null && session.chat_total > 0
        ? parseTranscript(session.transcript_md || "")
        : [];
    out =
      persisted.length > 0
        ? persisted
        : [
            topicAsUserMessage(session.topic || session.id),
            ...replayLiveLogToMessages(session.live_log, agentLabel),
          ];
  } else {
    out = [
      topicAsUserMessage(session.topic || session.id),
      ...parseTranscript(session.transcript_md || ""),
    ];
  }
  return mergePersistedChatWithLiveLog(out, session.live_log, agentLabel);
}
