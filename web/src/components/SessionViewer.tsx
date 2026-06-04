import { useEffect, useMemo, useState } from "react";
import type { AgentOption, SessionDetail } from "../api/client";
import {
  chatLineToMessage,
  parseTranscript,
  topicAsUserMessage,
  type ChatMessage,
} from "../utils/transcript";
import { buildPlanMetaView } from "../utils/planMeta";
import { analyzePlanRefWarnings } from "../utils/planRefWarnings";
import {
  CONTENT_TAB_SHORTCUT_EVENT,
  type ContentTab,
} from "../utils/desktopShortcuts";
import { roundDividerLabel } from "../utils/roundTopology";
import { ChatBubble } from "./ChatBubble";
import { ChatPaneBody } from "./ChatPaneBody";
import { ChatToolbar } from "./ChatToolbar";
import { PlanDocument } from "./PlanDocument";
import { PlanExecutePanel } from "./PlanExecutePanel";
import { CollapsibleGlassPanel } from "./CollapsibleGlassPanel";
import {
  ScrollToBottomButton,
  useMessagesScroll,
  useScrollToTop,
} from "./ScrollToBottomButton";

type Props = {
  session: SessionDetail | null;
  loading: boolean;
  sidebarOpen: boolean;
  onToggleSidebar: () => void;
  agents?: AgentOption[];
  onSessionRefresh?: () => void;
};

function renderChatLine(
  m: ChatMessage,
  highlightChatLine: number | null,
) {
  if ("roundDivider" in m && m.roundDivider) {
    return (
      <div key={m.id} className="chat-round-divider" aria-label={m.body}>
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
}

export function SessionViewer({
  session,
  loading,
  sidebarOpen,
  onToggleSidebar,
  agents = [],
  onSessionRefresh,
}: Props) {
  const [tab, setTab] = useState<"chat" | "plan">("chat");
  const [highlightChatLine, setHighlightChatLine] = useState<number | null>(
    null,
  );

  const messages: ChatMessage[] = useMemo(
    () =>
      !session
        ? []
        : session.chat && session.chat.length > 0
          ? (() => {
              const out: ChatMessage[] = [];
              let lastRound = 0;
              for (let i = 0; i < session.chat.length; i++) {
                const line = session.chat[i];
                const pr =
                  line.parallel_round ?? (line.role === "agent" ? 1 : 0);
                if (line.role === "agent" && pr > 1 && pr > lastRound) {
                  out.push({
                    id: `round-divider-${pr}`,
                    role: "system",
                    label: "",
                    body: roundDividerLabel(
                      pr,
                      Boolean(
                        (
                          session.run?.last_turn as
                            | { review_mode?: boolean }
                            | undefined
                        )?.review_mode,
                      ),
                    ),
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
            ],
    [session],
  );

  const { scrollRef, scrollElRef, showJumpButton, scrollToBottom } =
    useMessagesScroll([messages], tab === "chat", `${session?.id ?? "none"}:chat`);
  const { scrollRef: planScrollRef } = useScrollToTop(
    tab === "plan",
    `${session?.id ?? "none"}:plan`,
  );

  useEffect(() => {
    setTab("chat");
    setHighlightChatLine(null);
  }, [session?.id]);

  useEffect(() => {
    function onContentTabShortcut(event: Event) {
      const nextTab = (event as CustomEvent<ContentTab>).detail;
      if (nextTab === "chat" || nextTab === "plan") setTab(nextTab);
    }

    window.addEventListener(CONTENT_TAB_SHORTCUT_EVENT, onContentTabShortcut);
    return () =>
      window.removeEventListener(CONTENT_TAB_SHORTCUT_EVENT, onContentTabShortcut);
  }, []);

  useEffect(() => {
    if (highlightChatLine == null || tab !== "chat") return;
    const el = scrollElRef.current?.querySelector(
      `[data-chat-line="${highlightChatLine}"]`,
    ) as HTMLElement | null;
    el?.scrollIntoView({ behavior: "smooth", block: "center" });
    const t = window.setTimeout(() => setHighlightChatLine(null), 2600);
    return () => window.clearTimeout(t);
  }, [highlightChatLine, tab, messages, scrollElRef]);

  if (loading) {
    return (
      <ChatPaneBody className="chat-pane-body--readonly">
        <div className="empty-chat">불러오는 중…</div>
      </ChatPaneBody>
    );
  }

  if (!session) {
    return (
      <ChatPaneBody className="chat-pane-body--readonly">
        <div className="empty-chat">
          왼쪽에서 대화를 선택하거나 「새 대화」를 시작하세요.
        </div>
      </ChatPaneBody>
    );
  }

  const workflow =
    (session.run?.workflow_id as string) ||
    (session.meta?.workflow as string) ||
    "session";
  const planMd = session.plan_md || "";
  const planMeta = buildPlanMetaView(session.run);
  const planRefWarnings = analyzePlanRefWarnings(planMd, session.chat);
  const isClassicPipeline =
    workflow.includes("graph") ||
    workflow.includes("pipeline") ||
    workflow === "session";

  return (
    <ChatPaneBody className="chat-pane-body--readonly">
      <ChatToolbar
        sidebarOpen={sidebarOpen}
        onToggleSidebar={onToggleSidebar}
        title={session.topic || session.id}
        meta={
          isClassicPipeline ? "Planner → Critic → Scribe" : workflow
        }
      />

      <div className="view-tabs-bar">
        <div
          className="mac-segmented view-tabs-seg view-tabs-bar__leading"
          role="tablist"
        >
          <button
            type="button"
            role="tab"
            aria-selected={tab === "chat"}
            className={tab === "chat" ? "active" : ""}
            onClick={() => setTab("chat")}
            title="대화 (⌘1)"
          >
            대화
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={tab === "plan"}
            className={tab === "plan" ? "active" : ""}
            onClick={() => setTab("plan")}
            title="plan.md (⌘2)"
          >
            plan.md
          </button>
        </div>
      </div>

      {tab === "chat" ? (
        <div className="messages-scroll" ref={scrollRef}>
          {messages.length === 0 ? (
            <div className="empty-chat">대화 기록이 없습니다.</div>
          ) : (
            messages.map((m) => renderChatLine(m, highlightChatLine))
          )}
        </div>
      ) : (
        <div
          className="messages-scroll messages-scroll--document"
          ref={planScrollRef}
        >
          <div className="plan-tab-cluster">
            {planMd ? (
              <div
                className={`plan-meta-bar plan-meta-bar--${planMeta.freshness}`}
                role="status"
              >
                <div className="plan-meta-bar__row">
                  <span className="plan-meta-bar__line">
                    {planMeta.freshnessLabel !== "갱신 이력 없음"
                      ? planMeta.freshnessLabel
                      : `마지막 정리: ${planMeta.timeLabel} · ${planMeta.triggerLabel}`}
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
            {session?.id ? (
              <PlanExecutePanel
                sessionId={session.id}
                run={session.run}
                cursorReady={agents.some((a) => a.id === "cursor" && a.ready)}
                disabled={false}
                onChatRefClick={(lineNumber) => {
                  setTab("chat");
                  setHighlightChatLine(lineNumber - 1);
                }}
                onUpdated={() => onSessionRefresh?.()}
              />
            ) : null}
            <PlanDocument
              planMd={planMd || "(empty)"}
              skipExecuteSections
              onRefClick={(lineNumber) => {
                setTab("chat");
                setHighlightChatLine(lineNumber - 1);
              }}
            />
          </div>
        </div>
      )}

      {tab === "chat" ? (
        <ScrollToBottomButton
          visible={showJumpButton}
          onClick={scrollToBottom}
        />
      ) : null}
    </ChatPaneBody>
  );
}
