import type {
  RecoveryActionId,
  RecoveryItem,
  RecoveryKind,
} from "./recoveryItems";

export type RecoveryResolutionStatus =
  | "checking"
  | "resolved"
  | "still_blocked";

export type RecoveryRetryActionId = "focus_composer" | "restore_last_message";

export type RecoveryAttempt = {
  readonly id: string;
  readonly key: string;
  readonly actionId: RecoveryActionId;
  readonly item: RecoveryItem;
  readonly startedAt: number;
  readonly canRestoreLastMessage: boolean;
};

export type RecoveryResolutionEvent = {
  readonly id: string;
  readonly key: string;
  readonly kind: RecoveryKind;
  readonly title: string;
  readonly status: RecoveryResolutionStatus;
  readonly message: string;
  readonly actionId: RecoveryActionId;
  readonly createdAt: number;
  readonly canRestoreLastMessage: boolean;
};

export type RecoveryLifecycleView = {
  readonly activeItems: readonly RecoveryItem[];
  readonly resolvedEvents: readonly RecoveryResolutionEvent[];
  readonly retryState: {
    readonly canFocusComposer: boolean;
    readonly canRestoreLastMessage: boolean;
  };
};

export function recoveryItemKey(item: RecoveryItem): string {
  return `${item.kind}:${item.title}`;
}

export function createRecoveryAttempt(input: {
  readonly item: RecoveryItem;
  readonly actionId: RecoveryActionId;
  readonly canRestoreLastMessage: boolean;
}): RecoveryAttempt {
  const now = Date.now();
  return {
    id: `${recoveryItemKey(input.item)}:${input.actionId}:${now}`,
    key: recoveryItemKey(input.item),
    item: input.item,
    actionId: input.actionId,
    startedAt: now,
    canRestoreLastMessage: input.canRestoreLastMessage,
  };
}

function resolvedMessage(kind: RecoveryKind): string {
  switch (kind) {
    case "auth_expired":
    case "bridge_failed":
    case "partial_turn":
      return "재확인 완료. Composer에서 다시 보낼 수 있습니다.";
    case "run_failed":
      return "상태 확인이 완료되었습니다. 요청을 다시 시도할 수 있습니다.";
    case "run_lock":
      return "잠금 해제됨. 새 턴을 시작할 수 있습니다.";
    case "oracle_fail":
    case "discuss_recovery":
      return "복구 액션 실행됨. Work에서 검증 상태를 확인하세요.";
  }
}

function stillBlockedMessage(item: RecoveryItem): string {
  switch (item.kind) {
    case "auth_expired":
      return `재확인했지만 ${item.title} 문제가 남아 있습니다. Settings에서 로그인 상태를 확인하세요.`;
    case "bridge_failed":
      return "재연결했지만 Cursor bridge가 아직 막혀 있습니다. Settings Diagnostics를 확인하세요.";
    case "run_lock":
      return "잠금 해제 후에도 실행 잠금이 남아 있습니다. 상태를 다시 확인하세요.";
    case "partial_turn":
      return "재확인 후에도 최근 턴 오류가 남아 있습니다. Settings 또는 composer 상태를 확인하세요.";
    case "run_failed":
      return "재확인 후에도 요청 오류가 남아 있습니다. 세부 원인을 확인한 뒤 다시 시도하세요.";
    case "oracle_fail":
    case "discuss_recovery":
      return "복구 액션 후에도 검증/회복 상태가 남아 있습니다. Work에서 다음 액션을 확인하세요.";
  }
}

export function resolveRecoveryAttempt(input: {
  readonly attempt: RecoveryAttempt;
  readonly currentItems: readonly RecoveryItem[];
}): RecoveryResolutionEvent {
  const current = input.currentItems.find(
    (item) => recoveryItemKey(item) === input.attempt.key,
  );
  const status: RecoveryResolutionStatus =
    current == null ? "resolved" : "still_blocked";
  const item = current ?? input.attempt.item;
  return {
    id: `${input.attempt.id}:${status}`,
    key: input.attempt.key,
    kind: item.kind,
    title: item.title,
    status,
    message:
      status === "resolved"
        ? resolvedMessage(item.kind)
        : stillBlockedMessage(item),
    actionId: input.attempt.actionId,
    createdAt: Date.now(),
    canRestoreLastMessage: input.attempt.canRestoreLastMessage,
  };
}

export function buildRecoveryLifecycleView(input: {
  readonly activeItems: readonly RecoveryItem[];
  readonly resolvedEvents: readonly RecoveryResolutionEvent[];
  readonly composerSendLocked: boolean;
}): RecoveryLifecycleView {
  const latest = input.resolvedEvents[0] ?? null;
  return {
    activeItems: input.activeItems,
    resolvedEvents: input.resolvedEvents.slice(0, 3),
    retryState: {
      canFocusComposer: Boolean(latest),
      canRestoreLastMessage: Boolean(latest?.canRestoreLastMessage),
    },
  };
}
