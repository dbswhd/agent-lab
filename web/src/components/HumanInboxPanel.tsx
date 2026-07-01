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
  onResolved?: (detail?: { pendingCount: number }) => void;
  onBuildStarted?: () => void;
  onDismiss?: () => void;
  onOpenInbox?: () => void;
  disabled?: boolean;
  presentation?: "inline" | "popup" | "inspector" | "taskbar" | "composer";
  kindFilter?: "question" | "build" | "skill_draft";
  excludeKind?: "question" | "build" | "skill_draft";
  discussOnly?: boolean;
  hideInspectorLabel?: boolean;
  onRefClick?: (ref: string) => void;
  /** When true, pending rows are read-only (actions live in composer). */
  readOnly?: boolean;
  onFocusComposer?: () => void;
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

function inboxAgent(item: HumanInboxItem): AgentRole {
  const caller = (item.caller_agent ?? "").trim().toLowerCase();
  if (
    caller === "codex" ||
    caller === "claude" ||
    caller === "cursor" ||
    caller === "kimi_work"
  ) {
    return caller as AgentRole;
  }
  const src = (item.source ?? "cursor").toLowerCase();
  if (src === "codex" || src === "claude" || src === "cursor") return src;
  // Harvest/orchestrator items are synthesis, not a coding agent — show the
  // neutral scribe mark instead of falling back to the cursor brand logo.
  if (src === "orchestrator") return "scribe";
  if (isMcpSource(item)) return "scribe";
  return "cursor";
}

/** "Action needed" already implies these are unresolved — strip the noise
 *  prefix some harvest prompts carry so the real question leads. */
function cleanSubject(text: string): string {
  return text.replace(/^\s*미결\s*[:：]?\s*/, "").trim() || text;
}

function isDiscussHarvest(item: HumanInboxItem): boolean {
  return (item.source ?? "").toLowerCase() === "orchestrator";
}

function isMcpSource(item: HumanInboxItem): boolean {
  const src = (item.source ?? "").toLowerCase();
  return src.startsWith("mcp_") || src.includes("mcp");
}

function inboxSourceBadge(item: HumanInboxItem, ko: boolean): string | null {
  if (isDiscussHarvest(item)) return ko ? "Harvest" : "Harvest";
  if (isMcpSource(item)) return "MCP";
  const src = (item.source ?? "").trim();
  return src || null;
}

function inboxKindLabel(item: HumanInboxItem, ko: boolean): string {
  if (item.kind === "build") return ko ? "실행" : "Build";
  if (item.kind === "skill_draft") return ko ? "스킬" : "Skill";
  return ko ? "질문" : "Question";
}

function triggerBadge(
  trigger: string | null | undefined,
  ko: boolean,
): string | null {
  if (!trigger) return null;
  const map: Record<string, string> = ko
    ? {
        "T-Q0": "Clarifier",
        "T-Q1": "방향",
        "T-Q2": "Plan OPEN",
        "T-Q5": "수동",
      }
    : {
        "T-Q0": "Clarifier",
        "T-Q1": "Direction",
        "T-Q2": "Plan OPEN",
        "T-Q5": "Manual",
      };
  return map[trigger] ?? trigger;
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
  setFreeformDraft: React.Dispatch<
    React.SetStateAction<Record<string, string>>
  >;
  selectedDraft: Record<string, string>;
  setSelectedDraft: React.Dispatch<
    React.SetStateAction<Record<string, string>>
  >;
  onQuestion: (item: HumanInboxItem, optionId: string) => void;
  onFreeform: (item: HumanInboxItem) => void;
  onBuild: (item: HumanInboxItem, decision: "go" | "defer" | "reject") => void;
  onSkillDraft: (item: HumanInboxItem, decision: "approve" | "reject") => void;
  onDefer: (item: HumanInboxItem) => void;
  locale: "en" | "ko";
  onRefClick?: (ref: string) => void;
  readOnly?: boolean;
  hideHead?: boolean;
  flat?: boolean;
};

function InboxRow({
  item,
  planRevision,
  disabled,
  busyId,
  freeformDraft,
  setFreeformDraft,
  selectedDraft,
  setSelectedDraft,
  onQuestion,
  onFreeform,
  onBuild,
  onSkillDraft,
  onDefer,
  locale,
  onRefClick,
  readOnly = false,
  hideHead = false,
  flat = false,
}: InboxRowProps) {
  const ko = locale === "ko";
  const rawSubject =
    item.kind === "build" ? (item.summary ?? item.prompt) : item.prompt;
  const subject =
    item.kind === "question" ? cleanSubject(rawSubject) : rawSubject;
  const body =
    item.kind === "build" && item.prompt !== rawSubject ? item.prompt : null;
  const planStale =
    item.kind === "build" &&
    item.plan_revision &&
    planRevision &&
    item.plan_revision !== planRevision;
  const busy = disabled || busyId === item.id;
  const forkRow = item.kind === "question" && (item.options?.length ?? 0) >= 2;
  const sourceBadge = inboxSourceBadge(item, ko);
  const kindLabel = inboxKindLabel(item, ko);
  const trigger = triggerBadge(item.trigger, ko);
  // "Why this gate fired" — demoted from competing badges to one quiet sub-label.
  const why = [trigger, forkRow ? "FORK" : null].filter(Boolean).join(" · ");

  // Question answering — select an option, or type your own; submit confirms.
  const options = item.options ?? [];
  const draft = freeformDraft[item.id] ?? "";
  const selected = selectedDraft[item.id] ?? null;
  const canSubmit = !busy && (draft.trim().length > 0 || selected !== null);
  const pickOption = (optionId: string) => {
    setSelectedDraft((prev) => ({ ...prev, [item.id]: optionId }));
    // Selecting a choice and typing a custom answer are mutually exclusive.
    setFreeformDraft((prev) => {
      if (!prev[item.id]) return prev;
      const next = { ...prev };
      delete next[item.id];
      return next;
    });
  };
  const editDraft = (value: string) => {
    setFreeformDraft((prev) => ({ ...prev, [item.id]: value }));
    if (value && selected !== null) {
      setSelectedDraft((prev) => {
        const next = { ...prev };
        delete next[item.id];
        return next;
      });
    }
  };
  const submitAnswer = () => {
    if (!canSubmit) return;
    if (draft.trim().length > 0) void onFreeform(item);
    else if (selected !== null) void onQuestion(item, selected);
  };

  return (
    <div
      className={[
        "inbox-row",
        `inbox-row--${item.kind}`,
        forkRow ? "inbox-row--fork" : "",
        flat ? "inbox-row--flat" : "",
        isDiscussHarvest(item)
          ? "inbox-row--discuss"
          : "inbox-row--execute-lane",
      ]
        .filter(Boolean)
        .join(" ")}
    >
      {hideHead ? null : (
        <div className="inbox-row__head">
          <Avatar role={inboxAgent(item)} size={20} />
          <div className="inbox-row__headline">
            <span className="inbox-row__subject">{subject}</span>
            {why ? <span className="inbox-row__why">{why}</span> : null}
          </div>
          <span className="inbox-row__badges">
            {/* "Question" is implied by the answer affordance + panel header, so
              the kind badge only earns its place for build / skill rows. */}
            {item.kind !== "question" ? (
              <span
                className={`inbox-row__kind-badge inbox-row__kind-badge--${item.kind}`}
              >
                {kindLabel}
              </span>
            ) : null}
            {/* Provenance + timestamp are noise while answering — kept only on
              build / skill rows where the human is approving prior work. */}
            {item.kind !== "question" && sourceBadge ? (
              <span
                className={[
                  "inbox-row__source-badge",
                  isMcpSource(item) ? "inbox-row__source-badge--mcp" : "",
                  isDiscussHarvest(item)
                    ? "inbox-row__source-badge--harvest"
                    : "",
                ]
                  .filter(Boolean)
                  .join(" ")}
              >
                {sourceBadge}
              </span>
            ) : null}
          </span>
          {item.kind !== "question" ? (
            <span className="inbox-row__time">
              {formatInboxTime(item.created_at)}
            </span>
          ) : null}
        </div>
      )}
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
        <p className="inbox-row__body inbox-row__meta inbox-row__refs">
          <span className="inbox-row__refs-label">{ko ? "관련" : "Refs"}</span>
          {item.refs.map((ref) =>
            onRefClick ? (
              <button
                key={ref}
                type="button"
                className="inbox-row__ref-link"
                onClick={() => onRefClick(ref)}
              >
                {ref}
              </button>
            ) : (
              <span key={ref} className="inbox-row__ref-text">
                {ref}
              </span>
            ),
          )}
        </p>
      ) : null}
      {readOnly ? (
        <p className="inbox-row__body inbox-row__meta inbox-row__readonly-hint">
          {ko ? "Composer에서 처리" : "Handle in composer"}
        </p>
      ) : item.kind === "question" ? (
        <div
          className="inbox-row__answer"
          onKeyDown={(e) => {
            if (e.key === "Escape" && !busy) {
              e.preventDefault();
              void onDefer(item);
            }
          }}
        >
          {options.length > 0 ? (
            <ul className="inbox-choices" role="listbox" aria-label={subject}>
              {options.map((opt, index) => {
                const optionId = opt.id ?? opt.value ?? opt.label;
                const optionKey = `${item.id}:${optionId}:${index}`;
                const isSelected = selected === optionId;
                return (
                  <li key={optionKey} className="inbox-choices__item">
                    <button
                      type="button"
                      role="option"
                      aria-selected={isSelected}
                      className={[
                        "inbox-choice",
                        isSelected ? "inbox-choice--selected" : "",
                      ]
                        .filter(Boolean)
                        .join(" ")}
                      disabled={busy}
                      onClick={() => pickOption(optionId)}
                    >
                      <span className="inbox-choice__index" aria-hidden>
                        {index < 9 ? index + 1 : "•"}
                      </span>
                      <span className="inbox-choice__body">
                        <span className="inbox-choice__label">
                          {opt.label}
                          {opt.recommended ? (
                            <span className="inbox-choice__rec">
                              {ko ? "추천" : "Recommended"}
                            </span>
                          ) : null}
                        </span>
                        {opt.description ? (
                          <span className="inbox-choice__desc">
                            {opt.description}
                          </span>
                        ) : null}
                      </span>
                      <span className="inbox-choice__check" aria-hidden>
                        ✓
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          ) : null}
          <textarea
            className="inbox-row__input"
            rows={options.length > 0 ? 1 : 2}
            aria-label={ko ? "직접 답변 입력" : "Type your own answer"}
            placeholder={
              options.length > 0
                ? ko
                  ? "기타 — 직접 입력…"
                  : "Other — type your own…"
                : ko
                  ? "여기에 답변을 입력하세요"
                  : "Type your answer…"
            }
            value={draft}
            disabled={busy}
            onChange={(e) => editDraft(e.target.value)}
            onKeyDown={(e) => {
              if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
                e.preventDefault();
                submitAnswer();
              }
            }}
          />
          <div className="inbox-row__footer">
            <span className="inbox-row__footer-actions">
              <button
                type="button"
                className="btn btn--sm btn--ghost"
                disabled={busy}
                onClick={() => void onDefer(item)}
              >
                {ko ? "건너뛰기" : "Skip"}
                <kbd className="inbox-row__kbd">Esc</kbd>
              </button>
              <button
                type="button"
                className="btn btn--sm btn--primary"
                disabled={!canSubmit}
                aria-disabled={!canSubmit}
                title={
                  canSubmit
                    ? undefined
                    : ko
                      ? "선택지를 고르거나 답변을 입력하세요"
                      : "Pick an option or type an answer"
                }
                onClick={submitAnswer}
              >
                {ko ? "제출" : "Submit"}
                <kbd className="inbox-row__kbd">⌘↵</kbd>
              </button>
            </span>
          </div>
        </div>
      ) : item.kind === "skill_draft" ? (
        <div className="inbox-row__options inbox-row__options--build">
          <button
            type="button"
            className="btn btn--sm btn--ok"
            disabled={busy}
            onClick={() => void onSkillDraft(item, "approve")}
          >
            {ko ? "승격" : "Promote"}
          </button>
          <button
            type="button"
            className="btn btn--sm btn--danger"
            disabled={busy}
            onClick={() => void onSkillDraft(item, "reject")}
          >
            {ko ? "거절" : "Reject"}
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
            className="btn btn--sm btn--ghost"
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
  kindFilter,
  excludeKind,
  discussOnly = false,
  hideInspectorLabel = false,
  onRefClick,
  readOnly = false,
  onFocusComposer,
}: Props) {
  const { locale } = useLocale();
  const ko = locale === "ko";
  const [items, setItems] = useState<HumanInboxItem[]>([]);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [freeformDraft, setFreeformDraft] = useState<Record<string, string>>(
    {},
  );
  const [selectedDraft, setSelectedDraft] = useState<Record<string, string>>(
    {},
  );
  const [composerExpanded, setComposerExpanded] = useState(true);

  const reload = useCallback(async (): Promise<number> => {
    if (!sessionId) {
      setItems([]);
      return 0;
    }
    try {
      const payload = await fetchSessionInbox(sessionId);
      const rows = payload.human_inbox ?? [];
      setItems(rows);
      setError(null);
      return pendingItems(rows).length;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      throw e;
    }
  }, [sessionId]);

  useEffect(() => {
    void reload();
  }, [reload, reloadKey]);

  const pending = useMemo(() => pendingItems(items), [items]);
  const visibleItems = useMemo(() => {
    let rows = kindFilter
      ? items.filter((item) => item.kind === kindFilter)
      : items;
    if (excludeKind) {
      rows = rows.filter((item) => item.kind !== excludeKind);
    }
    if (discussOnly) {
      rows = rows.filter((item) => isDiscussHarvest(item));
    }
    return rows;
  }, [items, kindFilter, excludeKind, discussOnly]);
  const visiblePending = useMemo(
    () => pendingItems(visibleItems),
    [visibleItems],
  );
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
        const remaining = await reload();
        onResolved?.({ pendingCount: remaining });
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
        const remaining = await reload();
        onResolved?.({ pendingCount: remaining });
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        setBusyId(null);
      }
    },
    [sessionId, disabled, reload, onResolved],
  );

  const handleSkillDraft = useCallback(
    async (item: HumanInboxItem, decision: "approve" | "reject") => {
      if (!sessionId || disabled) return;
      setBusyId(item.id);
      try {
        await resolveInboxItem(sessionId, item.id, {
          selected: decision === "approve" ? ["approve"] : ["reject"],
        });
        const remaining = await reload();
        onResolved?.({ pendingCount: remaining });
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        setBusyId(null);
      }
    },
    [sessionId, disabled, reload, onResolved],
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
        const remaining = await reload();
        onResolved?.({ pendingCount: remaining });
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
        const remaining = await reload();
        onResolved?.({ pendingCount: remaining });
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
        items={visibleItems}
        error={error}
        disabled={disabled}
        busyId={busyId}
        planRevision={planRevision}
        freeformDraft={freeformDraft}
        setFreeformDraft={setFreeformDraft}
        selectedDraft={selectedDraft}
        setSelectedDraft={setSelectedDraft}
        onQuestion={handleQuestion}
        onFreeform={handleFreeform}
        onBuild={handleBuild}
        onSkillDraft={handleSkillDraft}
        onDefer={handleDefer}
        hideLabel={hideInspectorLabel}
        onRefClick={onRefClick}
        readOnly={readOnly}
        onFocusComposer={onFocusComposer}
      />
    );
  }

  if (visiblePending.length === 0) {
    if (presentation === "taskbar") {
      return (
        <div className="taskbar__empty human-inbox--taskbar-empty">
          {ko ? "Human gate 항목 없음" : "No human gate items"}
        </div>
      );
    }
    return null;
  }

  const questionCount = visiblePending.filter(
    (item) => item.kind === "question",
  ).length;
  const buildCount = visiblePending.filter(
    (item) => item.kind === "build",
  ).length;

  const title =
    presentation === "composer"
      ? ko
        ? "지금 할 일"
        : "Action needed"
      : presentation === "popup"
        ? visiblePending[0]?.kind === "build"
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
    selectedDraft,
    setSelectedDraft,
    onQuestion: handleQuestion,
    onFreeform: handleFreeform,
    onBuild: handleBuild,
    onSkillDraft: handleSkillDraft,
    onDefer: handleDefer,
    locale,
  };

  if (presentation === "composer") {
    const lead = visiblePending[0];
    const leadSubject = lead
      ? lead.kind === "question"
        ? cleanSubject(lead.prompt)
        : (lead.summary ?? lead.prompt)
      : "";
    const multi = visiblePending.length > 1;

    return (
      <div
        className={[
          "human-inbox human-inbox--composer human-inbox--composer-flat composer-dock-card composer-dock-card--composer",
          composerExpanded
            ? ""
            : "human-inbox--composer-collapsed composer-dock-card--collapsed",
        ]
          .filter(Boolean)
          .join(" ")}
        role="region"
        aria-label={ko ? "Human gate" : "Human gate"}
      >
        <button
          type="button"
          className="human-inbox__composer-toggle"
          aria-expanded={composerExpanded}
          onClick={() => setComposerExpanded((open) => !open)}
        >
          {lead ? <Avatar role={inboxAgent(lead)} size={20} /> : null}
          <span className="human-inbox__composer-headline composer-dock-card__headline">
            <span className="human-inbox__composer-subject composer-dock-card__subject">
              {leadSubject}
            </span>
            {!composerExpanded && multi ? (
              <span className="human-inbox__composer-meta composer-dock-card__meta">
                {ko
                  ? `외 ${visiblePending.length - 1}건`
                  : `+${visiblePending.length - 1} more`}
              </span>
            ) : null}
          </span>
          <span
            className={[
              "human-inbox__chevron",
              composerExpanded ? "human-inbox__chevron--open" : "",
            ]
              .filter(Boolean)
              .join(" ")}
            aria-hidden
          />
        </button>
        {composerExpanded ? (
          <>
            {error ? <div className="human-inbox__error">{error}</div> : null}
            <div className="human-inbox__items composer-dock-card__body">
              {visiblePending.map((item) => (
                <InboxRow
                  key={item.id}
                  item={item}
                  {...rowProps}
                  onRefClick={onRefClick}
                  hideHead={!multi && item.kind === "question"}
                  flat
                />
              ))}
            </div>
          </>
        ) : null}
      </div>
    );
  }

  return (
    <div
      className={["human-inbox", `human-inbox--${presentation}`].join(" ")}
      role={presentation === "popup" ? "dialog" : "region"}
      aria-label="Human Inbox"
      aria-modal={presentation === "popup" ? true : undefined}
    >
      {presentation !== "taskbar" ? (
        <div className="human-inbox__header">
          <span className="human-inbox__title">{title}</span>
          <span className="human-inbox__counts">
            {questionCount > 0
              ? ko
                ? `방향 ${questionCount}`
                : `${questionCount} question`
              : null}
            {questionCount > 0 && buildCount > 0 ? " · " : null}
            {buildCount > 0
              ? ko
                ? `실행 ${buildCount}`
                : `${buildCount} build`
              : null}
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
                  aria-label={
                    ko ? "Human Inbox popup 닫기" : "Dismiss Human Inbox popup"
                  }
                >
                  {ko ? "닫기" : "Dismiss"}
                </button>
              ) : null}
            </span>
          ) : null}
        </div>
      ) : null}
      {error ? <div className="human-inbox__error">{error}</div> : null}
      <div className="human-inbox__items">
        {visiblePending.map((item) => (
          <InboxRow
            key={item.id}
            item={item}
            {...rowProps}
            onRefClick={onRefClick}
          />
        ))}
      </div>
      {presentation === "taskbar" && onOpenInbox ? (
        <div className="human-inbox__taskbar-footer">
          <button type="button" className="btn btn--sm" onClick={onOpenInbox}>
            {ko ? "전체 Inbox" : "Full Inbox"}
          </button>
        </div>
      ) : null}
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
  setFreeformDraft: React.Dispatch<
    React.SetStateAction<Record<string, string>>
  >;
  selectedDraft: Record<string, string>;
  setSelectedDraft: React.Dispatch<
    React.SetStateAction<Record<string, string>>
  >;
  onQuestion: (item: HumanInboxItem, optionId: string) => void;
  onFreeform: (item: HumanInboxItem) => void;
  onBuild: (item: HumanInboxItem, decision: "go" | "defer" | "reject") => void;
  onSkillDraft: (item: HumanInboxItem, decision: "approve" | "reject") => void;
  onDefer: (item: HumanInboxItem) => void;
  hideLabel?: boolean;
  onRefClick?: (ref: string) => void;
  readOnly?: boolean;
  onFocusComposer?: () => void;
};

function InspectorInboxView({
  items,
  error,
  disabled,
  busyId,
  planRevision,
  freeformDraft,
  setFreeformDraft,
  selectedDraft,
  setSelectedDraft,
  onQuestion,
  onFreeform,
  onBuild,
  onSkillDraft,
  onDefer,
  hideLabel = false,
  onRefClick,
  readOnly = false,
  onFocusComposer,
}: InspectorInboxProps) {
  const { msg, locale } = useLocale();
  const ko = locale === "ko";

  return (
    <section
      className={
        hideLabel ? "ctx-section ctx-section--embedded" : "ctx-section"
      }
    >
      {hideLabel ? null : (
        <div className="ctx-section__label">{msg.humanInbox}</div>
      )}
      {readOnly ? (
        <div className="inbox-readonly-banner" role="status">
          <p className="inbox-readonly-banner__text">
            {ko
              ? "대기 중인 항목은 Composer에서 처리합니다. 여기서는 기록만 확인합니다."
              : "Pending items are handled in the composer. This view is history only."}
          </p>
          {onFocusComposer ? (
            <button
              type="button"
              className="btn btn--sm btn--primary"
              onClick={onFocusComposer}
            >
              {ko ? "Composer로 이동" : "Go to composer"}
            </button>
          ) : null}
        </div>
      ) : null}
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
              <div key={item.id} className="inbox-row inbox-row--resolved">
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
              selectedDraft={selectedDraft}
              setSelectedDraft={setSelectedDraft}
              onQuestion={onQuestion}
              onFreeform={onFreeform}
              onBuild={onBuild}
              onSkillDraft={onSkillDraft}
              onDefer={onDefer}
              locale={locale}
              onRefClick={onRefClick}
              readOnly={readOnly}
            />
          );
        })
      )}
    </section>
  );
}
