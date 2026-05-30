import { useEffect, useRef, useState } from "react";
import type { SessionDetail } from "../api/client";
import {
  chatLineToMessage,
  parseTranscript,
  topicAsUserMessage,
  type ChatMessage,
} from "../utils/transcript";
import { buildPlanMetaView } from "../utils/planMeta";
import { analyzePlanRefWarnings } from "../utils/planRefWarnings";
import { roundDividerLabel } from "../utils/roundTopology";
import { ChatBubble } from "./ChatBubble";
import { ChatPaneBody } from "./ChatPaneBody";
import { ChatToolbar } from "./ChatToolbar";
import { PlanDocument } from "./PlanDocument";
import { CollapsibleGlassPanel } from "./CollapsibleGlassPanel";

type Props = {
  session: SessionDetail | null;
  loading: boolean;
  sidebarOpen: boolean;
  onToggleSidebar: () => void;
};

export function SessionViewer({
  session,
  loading,
  sidebarOpen,
  onToggleSidebar,
}: Props) {
  const [tab, setTab] = useState<"chat" | "plan">("chat");
  const [highlightChatLine, setHighlightChatLine] = useState<number | null>(
    null,
  );
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (highlightChatLine == null || tab !== "chat") return;
    const el = scrollRef.current?.querySelector(
      `[data-chat-line="${highlightChatLine}"]`,
    ) as HTMLElement | null;
    el?.scrollIntoView({ behavior: "smooth", block: "center" });
    const t = window.setTimeout(() => setHighlightChatLine(null), 2600);
    return () => window.clearTimeout(t);
  }, [highlightChatLine, tab]);

  if (loading) {
    return (
      <ChatPaneBody>
        <div className="empty-chat">불러오는 중…</div>
      </ChatPaneBody>
    );
  }

  if (!session) {
    return (
      <ChatPaneBody>
        <div className="empty-chat">
          왼쪽에서 대화를 선택하거나 「새 대화」를 시작하세요.
        </div>
      </ChatPaneBody>
    );
  }

  const reviewModeHint = Boolean(
    (session.run?.last_turn as { review_mode?: boolean } | undefined)
      ?.review_mode,
  );

  const messages: ChatMessage[] =
    session.chat && session.chat.length > 0
      ? (() => {
          const out: ChatMessage[] = [];
          let lastRound = 0;
          for (let i = 0; i < session.chat.length; i++) {
            const line = session.chat[i];
            const pr = line.parallel_round ?? (line.role === "agent" ? 1 : 0);
            if (line.role === "agent" && pr > 1 && pr > lastRound) {
              out.push({
                id: `round-divider-${pr}`,
                role: "system",
                label: "",
                body: roundDividerLabel(pr, reviewModeHint),
                roundDivider: pr,
              });
              lastRound = pr;
            }
            out.push(chatLineToMessage(line, i));
          }
          return out;
        })()
      : [
          topicAsUserMessage(session.topic || session.id),
          ...parseTranscript(session.transcript_md || ""),
        ];

  const workflow =
    (session.run?.workflow_id as string) ||
    (session.meta?.workflow as string) ||
    "session";
  const planMd = session.plan_md || "";
  const planMeta = buildPlanMetaView(session.run);
  const planRefWarnings = analyzePlanRefWarnings(planMd, session.chat);

  return (
    <ChatPaneBody>
      <ChatToolbar
        sidebarOpen={sidebarOpen}
        onToggleSidebar={onToggleSidebar}
        title={session.topic || session.id}
        meta={workflow}
      />

      <div className="view-tabs-bar" role="tablist">
        <button
          type="button"
          role="tab"
          aria-selected={tab === "chat"}
          className={tab === "chat" ? "active" : ""}
          onClick={() => setTab("chat")}
        >
          대화
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === "plan"}
          className={tab === "plan" ? "active" : ""}
          onClick={() => setTab("plan")}
        >
          plan.md
        </button>
      </div>

      {tab === "chat" ? (
        <div className="messages-scroll" ref={scrollRef}>
          {messages.map((m) => {
            if ("roundDivider" in m && m.roundDivider) {
              return (
                <div
                  key={m.id}
                  className="chat-round-divider"
                  aria-label={m.body}
                >
                  {m.body}
                </div>
              );
            }
            const highlighted = highlightChatLine === m.chatLineIndex;
            return (
              <div
                key={m.id}
                className={[
                  "chat-line",
                  highlighted ? "chat-line--highlight" : undefined,
                ]
                  .filter(Boolean)
                  .join(" ")}
                {...(m.chatLineIndex != null
                  ? { "data-chat-line": m.chatLineIndex }
                  : {})}
              >
                <ChatBubble message={m} highlighted={highlighted} />
              </div>
            );
          })}
        </div>
      ) : (
        <div className="messages-scroll messages-scroll--document">
          {planMd ? (
            <div
              className={`plan-meta-bar plan-meta-bar--${planMeta.freshness}`}
              role="status"
            >
              <div className="plan-meta-bar__row">
                <span className="plan-meta-bar__line">
                  마지막 정리: {planMeta.timeLabel} · {planMeta.triggerLabel}
                  {planMeta.chatLineLabel
                    ? ` · ${planMeta.chatLineLabel}`
                    : ""}
                  {planMeta.freshness === "stale" &&
                  planMeta.messagesSincePlan != null
                    ? ` · 채팅 +${planMeta.messagesSincePlan}줄`
                    : ""}
                </span>
                <span className="plan-meta-bar__freshness">
                  {planMeta.freshness === "stale"
                    ? planMeta.freshnessLabel
                    : "최신"}
                </span>
              </div>
            </div>
          ) : null}
          {planRefWarnings.bannerText ? (
            <CollapsibleGlassPanel
              className="plan-ref-warn-panel"
              title="ref 경고"
              summary={planRefWarnings.bannerText}
              variant="warn"
              defaultOpen={false}
            >
              <p className="plan-ref-warn-panel__text">
                {planRefWarnings.bannerText}
              </p>
            </CollapsibleGlassPanel>
          ) : null}
          <PlanDocument
            planMd={planMd || "(empty)"}
            onRefClick={(lineNumber) => {
              setTab("chat");
              setHighlightChatLine(lineNumber - 1);
            }}
          />
        </div>
      )}
    </ChatPaneBody>
  );
}
