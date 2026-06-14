import { useLocale } from "../i18n/useLocale";

export type DiscussRecoveryState = {
  pending?: boolean;
  reason?: string | null;
  action_index?: number | null;
  started_at?: string | null;
};

type Props = {
  recovery: DiscussRecoveryState | null | undefined;
  busy?: boolean;
  onRunRecovery?: () => void;
  onOpenDiscussInbox?: () => void;
};

export function DiscussRecoveryBanner({
  recovery,
  busy,
  onRunRecovery,
  onOpenDiscussInbox,
}: Props) {
  const { msg } = useLocale();
  if (!recovery?.pending) return null;

  const reason = recovery.reason?.trim();
  const actionIndex = recovery.action_index;

  return (
    <div className="discuss-recovery-banner" role="status">
      <div className="discuss-recovery-banner__body">
        <strong>{msg.discussRecoveryTitle}</strong>
        <span className="discuss-recovery-banner__detail">
          {reason
            ? msg.discussRecoveryReason(reason)
            : msg.discussRecoveryDefault}
          {actionIndex != null ? ` · plan #${actionIndex}` : null}
        </span>
      </div>
      <span className="discuss-recovery-banner__actions">
        {onOpenDiscussInbox ? (
          <button
            type="button"
            className="btn btn--sm"
            onClick={onOpenDiscussInbox}
          >
            {msg.inboxDiscuss}
          </button>
        ) : null}
        {onRunRecovery ? (
          <button
            type="button"
            className="btn btn--sm btn--ok"
            disabled={busy}
            onClick={onRunRecovery}
          >
            {busy ? "…" : msg.discussRecoveryRun}
          </button>
        ) : null}
      </span>
    </div>
  );
}
