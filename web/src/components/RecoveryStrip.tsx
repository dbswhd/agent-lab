import { useEffect, useState } from "react";
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
      return "실행";
    case "blocking_send":
      return "전송";
    case "degraded_team":
      return "제한";
    case "informational":
      return "안내";
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
      return "확인 중";
    case "resolved":
      return "해결됨";
    case "still_blocked":
      return "아직 차단됨";
  }
}

function severityTone(item: RecoveryItem): string {
  switch (item.severity) {
    case "blocking_execute":
    case "blocking_send":
      return "차단";
    case "degraded_team":
      return "주의";
    case "informational":
      return "안내";
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
  const [showAll, setShowAll] = useState(false);
  useEffect(() => {
    if (items.length <= 1) setShowAll(false);
  }, [items.length]);
  if (items.length === 0 && resolvedEvents.length === 0) return null;

  const visibleItems = showAll ? items : items.slice(0, 1);

  return (
    <section
      className="recovery-strip"
      role={items.length > 0 ? "alert" : "status"}
      aria-label="복구 액션"
    >
      <header className="recovery-strip__head">
        <div className="recovery-strip__title-group">
          <span className="recovery-strip__eyebrow">
            {items[0] ? severityTone(items[0]) : "복구 완료"}
          </span>
          <strong>{items[0]?.title ?? "정상화됨"}</strong>
        </div>
        {items.length > 1 ? (
          <span className="recovery-strip__count">
            {items.length}개 확인 필요
          </span>
        ) : null}
        {onDismiss ? (
          <button
            type="button"
            className="recovery-strip__close"
            aria-label="복구 알림 닫기"
            title="닫기"
            onClick={onDismiss}
          >
            <svg
              width="14"
              height="14"
              viewBox="0 0 14 14"
              aria-hidden="true"
            >
              <path
                d="M3.2 3.2 10.8 10.8M10.8 3.2 3.2 10.8"
                fill="none"
                stroke="currentColor"
                strokeLinecap="round"
                strokeWidth="1.6"
              />
            </svg>
          </button>
        ) : null}
      </header>
      {items.length > 0 ? (
        <div className="recovery-strip__items">
          {visibleItems.map((item) => {
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
                  <p>{item.reason}</p>
                  {item.details ? (
                    <details className="recovery-item__details">
                      <summary>진단 정보</summary>
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
          {items.length > 1 ? (
            <button
              type="button"
              className="recovery-strip__more"
              aria-expanded={showAll}
              onClick={() => setShowAll((value) => !value)}
            >
              {showAll
                ? "나머지 상태 접기"
                : `다른 상태 ${items.length - 1}개 보기`}
            </button>
          ) : null}
        </div>
      ) : null}
      {resolvedEvents.length > 0 ? (
        <div className="recovery-strip__resolved" aria-label="최근 복구 결과">
          {resolvedEvents.slice(0, 1).map((event) => {
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
