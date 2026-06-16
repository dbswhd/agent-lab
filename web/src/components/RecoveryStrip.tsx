import type {
  RecoveryActionId,
  RecoveryItem,
} from "../utils/recoveryItems";

type Props = {
  readonly items: readonly RecoveryItem[];
  readonly busyActionId?: RecoveryActionId | null;
  readonly onAction: (actionId: RecoveryActionId, item: RecoveryItem) => void;
};

function severityLabel(item: RecoveryItem): string {
  switch (item.severity) {
    case "blocking_execute":
      return "Execute blocked";
    case "blocking_send":
      return "Send blocked";
    case "degraded_team":
      return "Team degraded";
    case "informational":
      return "Info";
  }
}

function actionBusyLabel(actionId: RecoveryActionId): string {
  switch (actionId) {
    case "reconnect_cursor":
    case "reconnect_claude":
      return "재확인 중...";
    case "release_lock":
      return "해제 중...";
    case "run_discuss_recovery":
      return "실행 중...";
    case "refresh_health":
      return "확인 중...";
    case "open_settings":
    case "open_work":
    case "open_inbox":
      return "여는 중...";
  }
}

export function RecoveryStrip({ items, busyActionId = null, onAction }: Props) {
  if (items.length === 0) return null;

  return (
    <section className="recovery-strip" aria-label="복구 액션">
      <header className="recovery-strip__head">
        <strong>Recovery</strong>
        <span>{items.length}개 확인 필요</span>
      </header>
      <div className="recovery-strip__items">
        {items.map((item) => {
          const secondaryAction = item.secondaryAction;
          const primaryBusy = busyActionId === item.primaryAction.id;
          const secondaryBusy =
            secondaryAction != null && busyActionId === secondaryAction.id;
          return (
            <article
              key={`${item.kind}:${item.title}`}
              className={`recovery-item recovery-item--${item.severity}`}
            >
              <div className="recovery-item__body">
                <span className="recovery-item__badge">
                  {severityLabel(item)}
                </span>
                <strong>{item.title}</strong>
                <p>{item.reason}</p>
                {item.details ? (
                  <details className="recovery-item__details">
                    <summary>details</summary>
                    <pre>{item.details}</pre>
                  </details>
                ) : null}
              </div>
              <div className="recovery-item__actions">
                <button
                  type="button"
                  className="btn btn--primary btn--sm"
                  disabled={primaryBusy}
                  onClick={() => onAction(item.primaryAction.id, item)}
                >
                  {primaryBusy
                    ? actionBusyLabel(item.primaryAction.id)
                    : item.primaryAction.label}
                </button>
                {secondaryAction ? (
                  <button
                    type="button"
                    className="btn btn--sm"
                    disabled={secondaryBusy}
                    onClick={() => onAction(secondaryAction.id, item)}
                  >
                    {secondaryBusy
                      ? actionBusyLabel(secondaryAction.id)
                      : secondaryAction.label}
                  </button>
                ) : null}
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}
