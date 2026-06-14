import { GateProfileChips } from "./GateProfileChips";
import { HumanInboxPanel } from "./HumanInboxPanel";
import { useLocale } from "../i18n/useLocale";

type Props = {
  sessionId: string | null;
  reloadKey?: number;
  planRevision?: string | null;
  discussPaused?: boolean;
  onResolved?: () => void;
  onBuildStarted?: () => void;
  disabled?: boolean;
  onOpenInbox?: () => void;
};

export function DiscussInboxPanel({
  sessionId,
  reloadKey = 0,
  planRevision = null,
  discussPaused = false,
  onResolved,
  onBuildStarted,
  disabled,
  onOpenInbox,
}: Props) {
  const { msg } = useLocale();

  if (!sessionId) return null;

  return (
    <section className="discuss-inbox-panel ctx-section">
      <div className="ctx-section__label">{msg.inboxDiscuss}</div>
      {discussPaused ? (
        <div className="discuss-inbox-panel__pause" role="status">
          {msg.inboxDiscussPausedBanner}
        </div>
      ) : null}
      <GateProfileChips sessionId={sessionId} compact reloadKey={reloadKey} />
      <p className="discuss-inbox-panel__hint">{msg.inboxDiscussHint}</p>
      <HumanInboxPanel
        sessionId={sessionId}
        reloadKey={reloadKey}
        planRevision={planRevision}
        onResolved={onResolved}
        onBuildStarted={onBuildStarted}
        disabled={disabled}
        onOpenInbox={onOpenInbox}
        presentation="inspector"
        kindFilter="question"
        discussOnly
        hideInspectorLabel
      />
    </section>
  );
}
