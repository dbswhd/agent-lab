import { useCallback, useEffect, useMemo, useRef, useState } from "react";
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
  disabled?: boolean;
  kindFilter?: "question" | "build" | "skill_draft" | "autonomy";
  excludeKind?: "question" | "build" | "skill_draft";
  discussOnly?: boolean;
  onRefClick?: (ref: string) => void;
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

/** Kinds resolved via the generic click-an-option UI (options[] -> selected: [id]) —
 * covers "question"/"autonomy" plus newer approve/reject-style kinds (N10a/C1) that
 * don't need a dedicated button layout like skill_draft's Promote/Reject. */
function usesGenericOptionsUi(kind: HumanInboxItem["kind"]): boolean {
  return (
    kind === "question" ||
    kind === "autonomy" ||
    kind === "correction_rule" ||
    kind === "retry_diagnosis" ||
    kind === "drift_audit" ||
    kind === "rule_sync"
  );
}

function inboxKindLabel(item: HumanInboxItem, ko: boolean): string {
  if (item.kind === "build") return ko ? "실행" : "Build";
  if (item.kind === "skill_draft") return ko ? "스킬" : "Skill";
  if (item.kind === "autonomy") return ko ? "자율도" : "Autonomy";
  if (item.kind === "correction_rule")
    return ko ? "교정 규칙" : "Correction rule";
  if (item.kind === "retry_diagnosis")
    return ko ? "재시도 진단" : "Retry diagnosis";
  if (item.kind === "drift_audit") return ko ? "드리프트 감사" : "Drift audit";
  if (item.kind === "rule_sync") return ko ? "규칙 동기화" : "Rule sync";
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
        "T-A0": "강등",
      }
    : {
        "T-Q0": "Clarifier",
        "T-Q1": "Direction",
        "T-Q2": "Plan OPEN",
        "T-Q5": "Manual",
        "T-A0": "Demotion",
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
  const forkRow =
    usesGenericOptionsUi(item.kind) && (item.options?.length ?? 0) >= 2;
  const sourceBadge = inboxSourceBadge(item, ko);
  const kindLabel = inboxKindLabel(item, ko);
  const trigger = triggerBadge(item.trigger, ko);
  const questionLead = usesGenericOptionsUi(item.kind)
    ? ko
      ? "답변 필요"
      : "Answer needed"
    : null;
  const approvalLead =
    !usesGenericOptionsUi(item.kind) && item.kind === "skill_draft"
      ? ko
        ? "승격 검토"
        : "Promotion review"
      : !usesGenericOptionsUi(item.kind)
        ? ko
          ? "승인 필요"
          : "Approval required"
        : null;
  // "Why this gate fired" — demoted from competing badges to one quiet sub-label.
  const why = [trigger, forkRow ? "FORK" : null].filter(Boolean).join(" · ");
  const createdAtLabel = formatInboxTime(item.created_at);
  const compactMeta = [
    questionLead ?? approvalLead,
    item.kind !== "question" ? kindLabel : null,
    sourceBadge,
    createdAtLabel || null,
  ]
    .filter(Boolean)
    .join(" · ");

  // Question answering — select an option, or type your own; submit confirms.
  const options = item.options ?? [];
  const optionRefs = useRef<Array<HTMLButtonElement | null>>([]);
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
  const handleOptionKeyDown = (
    event: React.KeyboardEvent<HTMLButtonElement>,
    index: number,
  ) => {
    const direction =
      event.key === "ArrowDown" || event.key === "ArrowRight"
        ? 1
        : event.key === "ArrowUp" || event.key === "ArrowLeft"
          ? -1
          : 0;
    const nextIndex =
      event.key === "Home"
        ? 0
        : event.key === "End"
          ? options.length - 1
          : direction
            ? (index + direction + options.length) % options.length
            : null;
    if (nextIndex === null || !options[nextIndex]) return;
    event.preventDefault();
    const nextOption = options[nextIndex];
    const nextOptionId = nextOption.id ?? nextOption.value ?? nextOption.label;
    pickOption(nextOptionId);
    optionRefs.current[nextIndex]?.focus();
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
            {flat && (questionLead ?? approvalLead) ? (
              <span className="inbox-row__lead">
                {questionLead ?? approvalLead}
              </span>
            ) : null}
            <span className="inbox-row__subject">{subject}</span>
            {why ? <span className="inbox-row__why">{why}</span> : null}
            {flat && compactMeta ? (
              <span className="inbox-row__meta-inline">{compactMeta}</span>
            ) : null}
          </div>
          {!flat ? (
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
          ) : null}
          {!flat && item.kind !== "question" ? (
            <span className="inbox-row__time">{createdAtLabel}</span>
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
      ) : usesGenericOptionsUi(item.kind) ? (
        <div
          className="inbox-row__answer inbox-row__answer--question"
          onKeyDown={(e) => {
            if (e.key === "Escape" && !busy) {
              e.preventDefault();
              void onDefer(item);
            }
          }}
        >
          {options.length > 0 ? (
            <ul
              className="inbox-choices"
              role="radiogroup"
              aria-label={subject}
            >
              {options.map((opt, index) => {
                const optionId = opt.id ?? opt.value ?? opt.label;
                const optionKey = `${item.id}:${optionId}:${index}`;
                const isSelected = selected === optionId;
                return (
                  <li key={optionKey} className="inbox-choices__item">
                    <button
                      type="button"
                      role="radio"
                      aria-checked={isSelected}
                      ref={(node) => {
                        optionRefs.current[index] = node;
                      }}
                      className={[
                        "inbox-choice",
                        isSelected ? "inbox-choice--selected" : "",
                      ]
                        .filter(Boolean)
                        .join(" ")}
                      disabled={busy}
                      onKeyDown={(event) => handleOptionKeyDown(event, index)}
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
            {!canSubmit ? (
              <span className="inbox-row__submit-hint">
                {ko
                  ? "선택지를 고르거나 직접 입력하세요"
                  : "Pick an option or type an answer"}
              </span>
            ) : null}
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
        <div className="inbox-row__options inbox-row__options--approval">
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
        <div className="inbox-row__options inbox-row__options--approval">
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
  disabled,
  kindFilter,
  excludeKind,
  discussOnly = false,
  onRefClick,
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

  if (visiblePending.length === 0) {
    return null;
  }

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
        "human-inbox human-inbox--composer composer-dock-card composer-dock-card--composer",
        composerExpanded ? "" : "composer-dock-card--collapsed",
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
          <span className="human-inbox__composer-kicker">
            {lead?.kind === "question"
              ? ko
                ? "질문에 답해주세요"
                : "Answer a question"
              : ko
                ? "결정이 필요합니다"
                : "Decision needed"}
          </span>
          <span className="human-inbox__composer-subject composer-dock-card__subject">
            {leadSubject}
          </span>
          <span className="human-inbox__composer-meta composer-dock-card__meta">
            {multi
              ? ko
                ? `${visiblePending.length}건 대기`
                : `${visiblePending.length} pending`
              : ko
                ? "답변하면 작업이 재개됩니다"
                : "Your answer resumes the workflow"}
          </span>
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
