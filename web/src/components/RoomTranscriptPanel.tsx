import { Fragment } from "react";
import type { AppNotification } from "../utils/notificationStore";
import type { LiveMsg } from "../run/runSessionRegistry";
import { ChatBubble, ReplyWaitingBubble } from "./ChatBubble";
import { ScrollToBottomButton } from "./ScrollToBottomButton";
import { TranscriptViewOptions } from "./TranscriptViewOptions";
import { TranscriptActivityDivider } from "./TranscriptActivityDivider";
import { isReplyWaitRole } from "../utils/transcript";

export type PendingReplyAgent = {
  id: string;
  role: LiveMsg["role"];
  label: string;
};

type Props = {
  sessionId: string | null;
  isNew: boolean;
  loading: boolean;
  running: boolean;
  showPeerChannel: boolean;
  onPeerChannelChange: (on: boolean) => void;
  visibleMessages: LiveMsg[];
  advisorRationales: (string | null)[];
  openDraftMessageIds: Set<string>;
  pendingReplyAgents: PendingReplyAgent[];
  highlightChatLine: number | null;
  locale: string;
  transcriptLoading: string;
  transcriptEmpty: string;
  transcriptEmptyHint: string;
  showJumpButton: boolean;
  forceScrollButton?: boolean;
  scrollToBottom: () => void;
  transcriptActive?: boolean;
  onActivityOpen?: (note: AppNotification) => void;
};

export function RoomTranscriptPanel({
  sessionId,
  isNew,
  loading = false,
  running,
  showPeerChannel,
  onPeerChannelChange,
  visibleMessages,
  advisorRationales,
  openDraftMessageIds,
  pendingReplyAgents,
  highlightChatLine,
  locale,
  transcriptLoading,
  transcriptEmpty,
  transcriptEmptyHint,
  showJumpButton,
  forceScrollButton,
  scrollToBottom,
  transcriptActive = true,
  onActivityOpen,
}: Props) {
  return (
    <>
      <div className="transcript transcript--console">
        {!isNew && sessionId ? (
          <TranscriptViewOptions
            showPeerChannel={showPeerChannel}
            onPeerChannelChange={onPeerChannelChange}
          />
        ) : null}
        {loading && !isNew && !running && visibleMessages.length === 0 ? (
          <div className="empty-state">
            <span className="empty-state__icon" aria-hidden>
              <svg
                viewBox="0 0 24 24"
                width="24"
                height="24"
                fill="none"
                stroke="currentColor"
                strokeWidth={1.5}
              >
                <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
              </svg>
            </span>
            <span className="empty-state__title">{transcriptLoading}</span>
          </div>
        ) : visibleMessages.length === 0 && !running ? (
          <div className="empty-state">
            <span className="empty-state__icon" aria-hidden>
              <svg
                viewBox="0 0 24 24"
                width="24"
                height="24"
                fill="none"
                stroke="currentColor"
                strokeWidth={1.5}
              >
                <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
              </svg>
            </span>
            <span className="empty-state__title">{transcriptEmpty}</span>
            <span className="empty-state__hint">{transcriptEmptyHint}</span>
          </div>
        ) : null}
        {(() => {
          let userTurnIdx = 0;
          return visibleMessages.map((m) => {
            if (m.activityMarker) {
              return (
                <TranscriptActivityDivider
                  key={m.id}
                  marker={m.activityMarker}
                  locale={locale}
                  onOpen={onActivityOpen}
                />
              );
            }
            if (m.roundDivider) {
              const roundLabel =
                locale === "ko"
                  ? `라운드 ${m.roundDivider}`
                  : `Round ${m.roundDivider}`;
              return (
                <div key={m.id} className="round-divider" aria-label={m.body}>
                  <span className="round-divider__label">{roundLabel}</span>
                </div>
              );
            }
            if (m.typing && isReplyWaitRole(m.role)) {
              return (
                <ReplyWaitingBubble
                  key={m.id}
                  agent={m.role}
                  label={m.label}
                  turnItems={m.turnItems}
                  body={m.body}
                />
              );
            }
            const highlighted = highlightChatLine === m.chatLineIndex;
            if (m.sent && !m.typing) {
              const rationale = advisorRationales[userTurnIdx] ?? null;
              userTurnIdx++;
              return (
                <Fragment key={m.id}>
                  <ChatBubble
                    message={m}
                    typing={m.typing}
                    highlighted={highlighted}
                    presentation="console"
                    draftDefaultOpen={openDraftMessageIds.has(m.id)}
                  />
                  {rationale ? (
                    <div className="advisor-hint" title={rationale}>
                      <span className="advisor-hint__label">advisor</span>
                      <span className="advisor-hint__text">{rationale}</span>
                    </div>
                  ) : null}
                </Fragment>
              );
            }
            return (
              <ChatBubble
                key={m.id}
                message={m}
                typing={m.typing}
                highlighted={highlighted}
                presentation="console"
                draftDefaultOpen={openDraftMessageIds.has(m.id)}
              />
            );
          });
        })()}
        {pendingReplyAgents.map((a) => (
          <ReplyWaitingBubble key={a.id} agent={a.role} label={a.label} />
        ))}
      </div>

      {transcriptActive ? (
        <ScrollToBottomButton
          visible={showJumpButton || Boolean(forceScrollButton)}
          onClick={scrollToBottom}
        />
      ) : null}
    </>
  );
}
