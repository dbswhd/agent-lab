import { GateProfileChips } from "./GateProfileChips";
import { HumanInboxPanel } from "./HumanInboxPanel";
import { DiscussRecoveryBanner, type DiscussRecoveryState } from "./DiscussRecoveryBanner";
import { useLocale } from "../i18n/useLocale";

type Props = {
  sessionId: string | null;
  reloadKey?: number;
  planRevision?: string | null;
  discussPaused?: boolean;
  discussRecovery?: DiscussRecoveryState | null;
  discussRecoveryBusy?: boolean;
  onRunDiscussRecovery?: () => void;
  onResolved?: () => void;
  onBuildStarted?: () => void;
  disabled?: boolean;
  onOpenInbox?: () => void;
  onRefClick?: (ref: string) => void;
};

export function DiscussInboxPanel({
  sessionId,
  reloadKey = 0,
  planRevision = null,
  discussPaused = false,
  discussRecovery = null,
  discussRecoveryBusy = false,
  onRunDiscussRecovery,
  onResolved,
  onBuildStarted,
  disabled,
  onOpenInbox,
  onRefClick,
}: Props) {
  const { msg } = useLocale();

  if (!sessionId) return null;

  return (
    <section className="discuss-inbox-panel ctx-section">
      <div className="ctx-section__label">{msg.inboxDiscuss}</div>
      <DiscussRecoveryBanner
        recovery={discussRecovery}
        busy={discussRecoveryBusy}
        onRunRecovery={onRunDiscussRecovery}
        onOpenDiscussInbox={onOpenInbox}
      />
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
        onRefClick={onRefClick}
        presentation="inspector"
        kindFilter="question"
        discussOnly
        hideInspectorLabel
      />
    </section>
  );
}
