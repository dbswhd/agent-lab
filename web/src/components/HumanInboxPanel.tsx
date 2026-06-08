import { useCallback, useEffect, useMemo, useState } from "react";
import {
  fetchSessionInbox,
  resolveInboxItem,
  runPlanDryRun,
  type HumanInboxItem,
} from "../api/client";
import { Avatar } from "./Avatar";
import { useLocale } from "../i18n/useLocale";
import type { AgentRole } from "../utils/transcript";

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

function inboxAgent(item: HumanInboxItem): AgentRole {
  const src = (item.source ?? "cursor").toLowerCase();
  if (src === "codex" || src === "claude" || src === "cursor") return src;
  return "cursor";
}

function formatInboxTime(iso?: string): string {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleTimeString(undefined, {
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return "";
  }
}

type InboxRowProps = {
  item: HumanInboxItem;
  planRevision: string | null;
  disabled?: boolean;
  busyId: string | null;
  freeformDraft: Record<string, string>;
  setFreeformDraft: React.Dispatch<React.SetStateAction<Record<string, string>>>;
  onQuestion: (item: HumanInboxItem, optionId: string) => void;
  onFreeform: (item: HumanInboxItem) => void;
  onBuild: (item: HumanInboxItem, decision: "go" | "defer" | "reject") => void;
  onDefer: (item: HumanInboxItem) => void;
  locale: "en" | "ko";
};

function InboxRow({
  item,
  planRevision,
  disabled,
  busyId,
  freeformDraft,
  setFreeformDraft,
  onQuestion,
  onFreeform,
  onBuild,
  onDefer,
  locale,
}: InboxRowProps) {
  const ko = locale === "ko";
  const subject =
    item.kind === "build" ? (item.summary ?? item.prompt) : item.prompt;
  const body =
    item.kind === "build" && item.prompt !== subject ? item.prompt : null;
  const planStale =
    item.kind === "build" &&
    item.plan_revision &&
    planRevision &&
    item.plan_revision !== planRevision;
  const busy = disabled || busyId === item.id;

  return (
    <div className={`inbox-row inbox-row--${item.kind}`}>
      <div className="inbox-row__head">
        <Avatar role={inboxAgent(item)} size={20} />
        <span className="inbox-row__subject">{subject}</span>
        <span className="inbox-row__time">{formatInboxTime(item.created_at)}</span>
      </div>
      {body ? <p className="inbox-row__body">{body}</p> : null}
      {item.action_ref ? (
        <p className="inbox-row__body inbox-row__meta">{item.action_ref}</p>
      ) : null}
      {planStale ? (
        <p className="inbox-row__body inbox-row__stale">
          {ko ? "plan 갱신됨 — 확인 후 GO" : "Plan updated — review before GO"}
        </p>
      ) : null}
      {item.refs && item.refs.length > 0 ? (
        <p className="inbox-row__body inbox-row__meta">{item.refs.join(" · ")}</p>
      ) : null}
      {item.kind === "question" ? (
        <div className="inbox-row__options">
          {(item.options ?? []).map((opt) => (
            <button
              key={opt.id}
              type="button"
              className="btn btn--sm"
              disabled={busy}
              onClick={() => void onQuestion(item, opt.id)}
            >
              {opt.label}
            </button>
          ))}
          {!hasQuestionOptions(item) ? (
            <>
              <textarea
                className="inbox-row__input"
                rows={2}
                placeholder={ko ? "방향을 입력…" : "Reply…"}
                value={freeformDraft[item.id] ?? ""}
                disabled={busy}
                onChange={(e) =>
                  setFreeformDraft((prev) => ({
                    ...prev,
                    [item.id]: e.target.value,
                  }))
                }
              />
              <button
                type="button"
                className="btn btn--sm btn--ok"
                disabled={busy || !(freeformDraft[item.id] ?? "").trim()}
                onClick={() => void onFreeform(item)}
              >
                {ko ? "답하기" : "Send"}
              </button>
            </>
          ) : null}
          <button
            type="button"
            className="btn btn--sm"
            disabled={busy}
            onClick={() => void onDefer(item)}
          >
            {ko ? "건너뛰기" : "Skip"}
          </button>
        </div>
      ) : (
        <div className="inbox-row__options inbox-row__options--build">
          <button
            type="button"
            className="btn btn--sm btn--ok"
            disabled={busy}
            onClick={() => void onBuild(item, "go")}
          >
            GO
          </button>
          <button
            type="button"
            className="btn btn--sm"
            disabled={busy}
            onClick={() => void onBuild(item, "defer")}
          >
            {ko ? "보류" : "Defer"}
          </button>
          <button
            type="button"
            className="btn btn--sm btn--danger"
            disabled={busy}
            onClick={() => void onBuild(item, "reject")}
          >
            {ko ? "거부" : "Reject"}
          </button>
        </div>
      )}
    </div>
  );
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
  const { locale } = useLocale();
  const ko = locale === "ko";
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

  if (!sessionId) {
    return null;
  }

  if (presentation === "inspector") {
    return (
      <InspectorInboxView
        items={items}
        error={error}
        disabled={disabled}
        busyId={busyId}
        planRevision={planRevision}
        freeformDraft={freeformDraft}
        setFreeformDraft={setFreeformDraft}
        onQuestion={handleQuestion}
        onFreeform={handleFreeform}
        onBuild={handleBuild}
        onDefer={handleDefer}
      />
    );
  }

  if (pending.length === 0) {
    return null;
  }

  const questionCount = pending.filter((item) => item.kind === "question").length;
  const buildCount = pending.filter((item) => item.kind === "build").length;

  const title =
    presentation === "popup"
      ? pending[0]?.kind === "build"
        ? ko
          ? "Build 승인 필요"
          : "Build approval required"
        : ko
          ? "질문에 답해야 합니다"
          : "Answer required"
      : "Human Inbox";

  const rowProps = {
    planRevision,
    disabled,
    busyId,
    freeformDraft,
    setFreeformDraft,
    onQuestion: handleQuestion,
    onFreeform: handleFreeform,
    onBuild: handleBuild,
    onDefer: handleDefer,
    locale,
  };

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
          {questionCount > 0 ? (ko ? `방향 ${questionCount}` : `${questionCount} question`) : null}
          {questionCount > 0 && buildCount > 0 ? " · " : null}
          {buildCount > 0 ? (ko ? `실행 ${buildCount}` : `${buildCount} build`) : null}
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
                aria-label={ko ? "Human Inbox popup 닫기" : "Dismiss Human Inbox popup"}
              >
                {ko ? "닫기" : "Dismiss"}
              </button>
            ) : null}
          </span>
        ) : null}
      </div>
      {error ? <div className="human-inbox__error">{error}</div> : null}
      <div className="human-inbox__items">
        {pending.map((item) => (
          <InboxRow key={item.id} item={item} {...rowProps} />
        ))}
      </div>
    </div>
  );
}

type InspectorInboxProps = {
  items: HumanInboxItem[];
  error: string | null;
  disabled?: boolean;
  busyId: string | null;
  planRevision: string | null;
  freeformDraft: Record<string, string>;
  setFreeformDraft: React.Dispatch<React.SetStateAction<Record<string, string>>>;
  onQuestion: (item: HumanInboxItem, optionId: string) => void;
  onFreeform: (item: HumanInboxItem) => void;
  onBuild: (item: HumanInboxItem, decision: "go" | "defer" | "reject") => void;
  onDefer: (item: HumanInboxItem) => void;
};

function InspectorInboxView({
  items,
  error,
  disabled,
  busyId,
  planRevision,
  freeformDraft,
  setFreeformDraft,
  onQuestion,
  onFreeform,
  onBuild,
  onDefer,
}: InspectorInboxProps) {
  const { msg, locale } = useLocale();

  return (
    <section className="ctx-section">
      <div className="ctx-section__label">{msg.humanInbox}</div>
      {error ? <div className="ctx-empty">{error}</div> : null}
      {items.length === 0 ? (
        <div className="ctx-empty">{msg.inboxEmpty}</div>
      ) : (
        items.map((item) => {
          if (item.status !== "pending") {
            const subject =
              item.kind === "build"
                ? (item.summary ?? item.prompt)
                : item.prompt;
            return (
              <div
                key={item.id}
                className="inbox-row inbox-row--resolved"
              >
                <div className="inbox-row__head">
                  <Avatar role={inboxAgent(item)} size={20} />
                  <span className="inbox-row__subject">{subject}</span>
                  <span className="inbox-row__time">
                    {formatInboxTime(item.created_at)}
                  </span>
                </div>
                <p className="inbox-row__body">{item.status}</p>
              </div>
            );
          }
          return (
            <InboxRow
              key={item.id}
              item={item}
              planRevision={planRevision}
              disabled={disabled}
              busyId={busyId}
              freeformDraft={freeformDraft}
              setFreeformDraft={setFreeformDraft}
              onQuestion={onQuestion}
              onFreeform={onFreeform}
              onBuild={onBuild}
              onDefer={onDefer}
              locale={locale}
            />
          );
        })
      )}
    </section>
  );
}
