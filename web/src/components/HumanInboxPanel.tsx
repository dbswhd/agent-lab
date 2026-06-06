import { useCallback, useEffect, useMemo, useState } from "react";
import {
  fetchSessionInbox,
  resolveInboxItem,
  runPlanDryRun,
  type HumanInboxItem,
} from "../api/client";

type Props = {
  sessionId: string | null;
  reloadKey?: number;
  planRevision?: string | null;
  onResolved?: () => void;
  onBuildStarted?: () => void;
  onDismiss?: () => void;
  onOpenInbox?: () => void;
  disabled?: boolean;
  presentation?: "inline" | "popup" | "inspector";
};

function pendingItems(items: HumanInboxItem[]): HumanInboxItem[] {
  return items.filter((item) => item.status === "pending");
}

function parseActionRef(
  ref: string | null | undefined,
): { kind: string; index: number } | null {
  if (!ref) return null;
  const [kind, idx] = ref.split(":");
  const index = Number.parseInt(idx ?? "", 10);
  if (!kind || Number.isNaN(index) || index < 1) return null;
  return { kind, index };
}

function hasQuestionOptions(item: HumanInboxItem): boolean {
  return (item.options?.length ?? 0) > 0;
}

export function HumanInboxPanel({
  sessionId,
  reloadKey = 0,
  planRevision = null,
  onResolved,
  onBuildStarted,
  onDismiss,
  onOpenInbox,
  disabled,
  presentation = "inline",
}: Props) {
  const [items, setItems] = useState<HumanInboxItem[]>([]);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [freeformDraft, setFreeformDraft] = useState<Record<string, string>>({});

  const reload = useCallback(async () => {
    if (!sessionId) {
      setItems([]);
      return;
    }
    try {
      const payload = await fetchSessionInbox(sessionId);
      setItems(payload.human_inbox ?? []);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [sessionId]);

  useEffect(() => {
    void reload();
  }, [reload, reloadKey]);

  const pending = useMemo(() => pendingItems(items), [items]);
  const hasPending = pending.length > 0;

  useEffect(() => {
    if (!sessionId || !hasPending) return;
    const timer = window.setInterval(() => {
      void reload();
    }, 2500);
    return () => window.clearInterval(timer);
  }, [sessionId, hasPending, reload]);

  const handleQuestion = useCallback(
    async (item: HumanInboxItem, optionId: string) => {
      if (!sessionId || disabled) return;
      setBusyId(item.id);
      try {
        await resolveInboxItem(sessionId, item.id, { selected: [optionId] });
        await reload();
        onResolved?.();
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        setBusyId(null);
      }
    },
    [sessionId, disabled, reload, onResolved],
  );

  const handleFreeform = useCallback(
    async (item: HumanInboxItem) => {
      if (!sessionId || disabled) return;
      const note = (freeformDraft[item.id] ?? "").trim();
      if (!note) return;
      setBusyId(item.id);
      try {
        await resolveInboxItem(sessionId, item.id, { note });
        setFreeformDraft((prev) => {
          const next = { ...prev };
          delete next[item.id];
          return next;
        });
        await reload();
        onResolved?.();
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        setBusyId(null);
      }
    },
    [sessionId, disabled, freeformDraft, reload, onResolved],
  );

  const handleBuild = useCallback(
    async (item: HumanInboxItem, decision: "go" | "defer" | "reject") => {
      if (!sessionId || disabled) return;
      setBusyId(item.id);
      try {
        // GO → trigger dry-run first; only resolve the item if it starts.
        // The dry-run endpoint re-checks gates (objection/snapshot/pre_execute)
        // and throws on 409, leaving the item pending for retry/defer.
        if (decision === "go") {
          const action = parseActionRef(item.action_ref);
          if (action) {
            await runPlanDryRun(sessionId, {
              actionIndex: action.index,
              actionKind: action.kind,
            });
          }
        }
        await resolveInboxItem(sessionId, item.id, { decision });
        await reload();
        onResolved?.();
        if (decision === "go") onBuildStarted?.();
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        setBusyId(null);
      }
    },
    [sessionId, disabled, reload, onResolved, onBuildStarted],
  );

  const handleDefer = useCallback(
    async (item: HumanInboxItem) => {
      if (!sessionId || disabled) return;
      setBusyId(item.id);
      try {
        await resolveInboxItem(sessionId, item.id, {
          status: "deferred",
          decision: "defer",
        });
        await reload();
        onResolved?.();
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        setBusyId(null);
      }
    },
    [sessionId, disabled, reload, onResolved],
  );

  if (!sessionId || pending.length === 0) {
    return null;
  }

  const questionCount = pending.filter((item) => item.kind === "question").length;
  const buildCount = pending.filter((item) => item.kind === "build").length;

  const title =
    presentation === "popup"
      ? pending[0]?.kind === "build"
        ? "Build 승인 필요"
        : "질문에 답해야 합니다"
      : "Human Inbox";

  return (
    <div
      className={[
        "human-inbox",
        `human-inbox--${presentation}`,
      ].join(" ")}
      role={presentation === "popup" ? "dialog" : "region"}
      aria-label="Human Inbox"
      aria-modal={presentation === "popup" ? true : undefined}
    >
      <div className="human-inbox__header">
        <span className="human-inbox__title">{title}</span>
        <span className="human-inbox__counts">
          {questionCount > 0 ? `방향 ${questionCount}` : null}
          {questionCount > 0 && buildCount > 0 ? " · " : null}
          {buildCount > 0 ? `실행 ${buildCount}` : null}
        </span>
        {presentation === "popup" ? (
          <span className="human-inbox__header-actions">
            {onOpenInbox ? (
              <button
                type="button"
                className="human-inbox__header-btn"
                onClick={onOpenInbox}
              >
                Inbox
              </button>
            ) : null}
            {onDismiss ? (
              <button
                type="button"
                className="human-inbox__header-btn"
                onClick={onDismiss}
                aria-label="Human Inbox popup 닫기"
              >
                닫기
              </button>
            ) : null}
          </span>
        ) : null}
      </div>
      {error ? <div className="human-inbox__error">{error}</div> : null}
      <div className="human-inbox__items">
        {pending.map((item) => (
          <div
            key={item.id}
            className={`human-inbox__item human-inbox__item--${item.kind}`}
          >
            <div className="human-inbox__prompt">
              {item.kind === "build" ? item.summary ?? item.prompt : item.prompt}
            </div>
            {item.action_ref ? (
              <div className="human-inbox__meta">{item.action_ref}</div>
            ) : null}
            {item.kind === "build" &&
            item.plan_revision &&
            planRevision &&
            item.plan_revision !== planRevision ? (
              <div className="human-inbox__meta human-inbox__plan-stale">
                plan 갱신됨 — 확인
              </div>
            ) : null}
            {item.refs && item.refs.length > 0 ? (
              <div className="human-inbox__meta human-inbox__refs">
                {item.refs.join(" · ")}
              </div>
            ) : null}
            {item.kind === "question" ? (
              <div className="human-inbox__options">
                {(item.options ?? []).map((opt) => (
                  <button
                    key={opt.id}
                    type="button"
                    className="human-inbox__option"
                    disabled={disabled || busyId === item.id}
                    onClick={() => void handleQuestion(item, opt.id)}
                  >
                    <span className="human-inbox__option-label">{opt.label}</span>
                    {opt.description ? (
                      <span className="human-inbox__option-desc">{opt.description}</span>
                    ) : null}
                  </button>
                ))}
                {!hasQuestionOptions(item) ? (
                  <div className="human-inbox__freeform">
                    <textarea
                      className="human-inbox__freeform-input"
                      rows={2}
                      placeholder="방향을 입력…"
                      value={freeformDraft[item.id] ?? ""}
                      disabled={disabled || busyId === item.id}
                      onChange={(e) =>
                        setFreeformDraft((prev) => ({
                          ...prev,
                          [item.id]: e.target.value,
                        }))
                      }
                    />
                    <button
                      type="button"
                      className="human-inbox__freeform-submit"
                      disabled={
                        disabled ||
                        busyId === item.id ||
                        !(freeformDraft[item.id] ?? "").trim()
                      }
                      onClick={() => void handleFreeform(item)}
                    >
                      답하기
                    </button>
                  </div>
                ) : null}
                <button
                  type="button"
                  className="human-inbox__skip"
                  disabled={disabled || busyId === item.id}
                  onClick={() => void handleDefer(item)}
                >
                  건너뛰기
                </button>
              </div>
            ) : (
              <div className="human-inbox__build-actions">
                <button
                  type="button"
                  className="human-inbox__go"
                  disabled={disabled || busyId === item.id}
                  onClick={() => void handleBuild(item, "go")}
                >
                  GO
                </button>
                <button
                  type="button"
                  className="human-inbox__defer"
                  disabled={disabled || busyId === item.id}
                  onClick={() => void handleBuild(item, "defer")}
                >
                  보류
                </button>
                <button
                  type="button"
                  className="human-inbox__reject"
                  disabled={disabled || busyId === item.id}
                  onClick={() => void handleBuild(item, "reject")}
                >
                  거부
                </button>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
