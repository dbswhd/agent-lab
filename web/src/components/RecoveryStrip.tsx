import type { RecoveryActionId, RecoveryItem } from "../utils/recoveryItems";
import type {
  RecoveryResolutionEvent,
  RecoveryRetryActionId,
} from "../utils/recoveryLifecycle";

type Props = {
  readonly items: readonly RecoveryItem[];
  readonly resolvedEvents?: readonly RecoveryResolutionEvent[];
  readonly canRetrySend?: boolean;
  readonly busyActionId?: RecoveryActionId | null;
  readonly onAction: (actionId: RecoveryActionId, item: RecoveryItem) => void;
  readonly onRetryAction?: (
    actionId: RecoveryRetryActionId,
    event: RecoveryResolutionEvent,
  ) => void;
  readonly onDismiss?: () => void;
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
    case "reconnect_kimi_work":
      return "재확인 중...";
    case "release_lock":
      return "해제 중...";
    case "retry_failed_agents":
      return "재시도 중...";
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

function resolutionLabel(event: RecoveryResolutionEvent): string {
  switch (event.status) {
    case "checking":
      return "Checking";
    case "resolved":
      return "Resolved";
    case "still_blocked":
      return "Still blocked";
  }
}

function resolutionActionLabel(event: RecoveryResolutionEvent): string {
  if (event.kind === "oracle_fail" || event.kind === "discuss_recovery") {
    return "Work 열기";
  }
  return event.canRestoreLastMessage
    ? "이전 메시지 다시 넣기"
    : "Composer로 돌아가기";
}

export function RecoveryStrip({
  items,
  resolvedEvents = [],
  canRetrySend = false,
  busyActionId = null,
  onAction,
  onRetryAction,
  onDismiss,
}: Props) {
  if (items.length === 0 && resolvedEvents.length === 0) return null;

  return (
    <section
      className="recovery-strip"
      role={items.length > 0 ? "alert" : "status"}
      aria-label="복구 액션"
    >
      <header className="recovery-strip__head">
        <strong>복구</strong>
        <span className="recovery-strip__count">
          {items.length > 0 ? `${items.length}개 확인 필요` : "최근 복구 완료"}
        </span>
        {onDismiss ? (
          <button
            type="button"
            className="recovery-strip__close"
            aria-label="복구 알림 닫기"
            title="닫기"
            onClick={onDismiss}
          >
            ✕
          </button>
        ) : null}
      </header>
      {items.length > 0 ? (
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
      ) : null}
      {resolvedEvents.length > 0 ? (
        <div className="recovery-strip__resolved" aria-label="최근 복구 결과">
          {resolvedEvents.slice(0, 3).map((event) => {
            const workEvent =
              event.kind === "oracle_fail" || event.kind === "discuss_recovery";
            const actionId: RecoveryRetryActionId =
              event.canRestoreLastMessage && !workEvent
                ? "restore_last_message"
                : "focus_composer";
            return (
              <article
                key={event.id}
                className={`recovery-resolution recovery-resolution--${event.status}`}
              >
                <div className="recovery-resolution__body">
                  <span className="recovery-item__badge">
                    {resolutionLabel(event)}
                  </span>
                  <strong>{event.title}</strong>
                  <p>{event.message}</p>
                </div>
                {event.status === "resolved" && onRetryAction ? (
                  <button
                    type="button"
                    className="btn btn--sm"
                    disabled={!canRetrySend && !workEvent}
                    onClick={() => onRetryAction(actionId, event)}
                  >
                    {resolutionActionLabel(event)}
                  </button>
                ) : null}
              </article>
            );
          })}
        </div>
      ) : null}
    </section>
  );
}
