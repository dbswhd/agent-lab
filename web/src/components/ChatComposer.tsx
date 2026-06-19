import { useMemo, useRef, useState, useEffect, type ReactNode } from "react";
import { ComposerPlanToggle } from "./ComposerPlanToggle";
import { ComposerTurnPicker } from "./ComposerTurnPicker";
import { ComposerMentionMenu } from "./ComposerMentionMenu";
import {
  mentionQueryAtCursor,
  useComposerMentionPaths,
} from "../hooks/useComposerMentionPaths";
import { SlashCommandMenu } from "./SlashCommandMenu";
import type { SlashCommandRecord } from "../api/client";
import type { ComposerTurnProfile } from "../utils/turnProfile";
import type { Locale } from "../i18n/locale";
import { useLocale } from "../i18n/useLocale";

export type PendingFile = { id: string; file: File };

type ObjectionNotice = {
  message: string;
  objectionId: string;
  actionIndex?: number;
};

type Props = {
  value: string;
  onChange: (v: string) => void;
  onSend: () => void;
  disabled?: boolean;
  /** Blocks send only (input may stay enabled while a run is winding down). */
  sendDisabled?: boolean;
  placeholder?: string;
  files: PendingFile[];
  onFilesAdd: (files: FileList | File[]) => void;
  onFileRemove: (id: string) => void;
  showAttach?: boolean;
  toolbar?: ReactNode;
  className?: string;
  turnProfile?: ComposerTurnProfile;
  onTurnProfileChange?: (profile: ComposerTurnProfile) => void;
  planAfterSend?: boolean;
  onPlanAfterSendChange?: (on: boolean) => void;
  /** Lock Plan toggle (e.g. HUMAN_PENDING — approve/reject first). */
  planToggleDisabled?: boolean;
  executeDisabled?: boolean;
  pendingExecuteCount?: number;
  /** @deprecated Plan stale notices live on the Work tab. */
  planStaleNotice?: string | null;
  objectionNotice?: ObjectionNotice | null;
  onFocusObjection?: (objectionId: string, actionIndex?: number) => void;
  /** When set, replaces joined description + costHint (prototype one-liner). */
  turnHint?: string | null;
  locale?: Locale;
  /** Hide textarea/send (mode picker stays visible). */
  inputHidden?: boolean;
  /** Secondary line under mode chip (off = less plan noise on chat). */
  showModeChipHint?: boolean;
  /** Always-visible mode chip subline (prototype `mode_*_hint`). */
  modeChipHint?: string | null;
  running?: boolean;
  onStop?: () => void;
  /** Current room turn mode (토론 / 정리 / 합의). */
  modeChip?: string | null;
  modeChipVariant?: "discuss" | "plan" | "consensus";
  /** New session — plan scribe timing hint. */
  isNewSession?: boolean;
  slashCommands?: SlashCommandRecord[];
  onSlashExecute?: (command: SlashCommandRecord) => void;
  /** When set, `@` opens a workspace file mention picker (Files tab roots). */
  sessionId?: string | null;
};

/**
 * Rebuilt chat composer. ALL behavior + the full Props contract preserved.
 * Vertical order: attachments → mode chip → turn picker
 * → plan-stale notice → objection alert → input row.
 * New class system; logic (slash filter/keydown, stop) untouched.
 */
export function ChatComposer({
  value,
  onChange,
  onSend,
  disabled,
  sendDisabled,
  placeholder = "메시지",
  files,
  onFilesAdd,
  onFileRemove,
  showAttach = true,
  toolbar,
  className,
  turnProfile,
  onTurnProfileChange,
  planAfterSend = false,
  onPlanAfterSendChange,
  planToggleDisabled = false,
  executeDisabled: _executeDisabled,
  pendingExecuteCount: _pendingExecuteCount,
  objectionNotice,
  onFocusObjection,
  turnHint,
  locale = "en",
  inputHidden = false,
  showModeChipHint = false,
  modeChipHint,
  running = false,
  onStop,
  modeChip,
  modeChipVariant,
  isNewSession = false,
  slashCommands = [],
  onSlashExecute,
  sessionId = null,
}: Props) {
  const { msg: localeMsg } = useLocale();
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [slashHighlight, setSlashHighlight] = useState(0);
  const [mentionCursor, setMentionCursor] = useState(0);
  const {
    paths: mentionPaths,
    loading: mentionLoading,
    ensureLoaded,
  } = useComposerMentionPaths(sessionId);

  useEffect(() => {
    const el = inputRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 180)}px`;
  }, [value]);

  const slashQuery = value.slice(1).split(/\s/)[0] ?? "";
  const slashFiltered = useMemo(() => {
    if (!value.startsWith("/")) return [];
    const query = slashQuery.toLowerCase();
    const rows = slashCommands.filter((c) => c.enabled !== false);
    if (!query) return rows;
    return rows.filter(
      (c) =>
        c.slash.toLowerCase().includes(query) ||
        c.label.toLowerCase().includes(query),
    );
  }, [slashCommands, slashQuery, value]);

  const mentionQuery = useMemo(() => {
    if (!sessionId) return null;
    return mentionQueryAtCursor(value, mentionCursor);
  }, [sessionId, value, mentionCursor]);

  useEffect(() => {
    if (mentionQuery != null) void ensureLoaded();
  }, [mentionQuery, ensureLoaded]);

  function applyMention(path: string) {
    const el = inputRef.current;
    const cursor = el?.selectionStart ?? value.length;
    const head = value.slice(0, cursor);
    const tail = value.slice(cursor);
    const replaced = head.replace(/(?:^|\s)@([^\s@]*)$/, (m) =>
      m.startsWith(" ") ? ` @${path} ` : `@${path} `,
    );
    onChange(`${replaced}${tail}`);
    requestAnimationFrame(() => {
      const next = inputRef.current;
      if (!next) return;
      const pos = replaced.length;
      next.focus();
      next.setSelectionRange(pos, pos);
      setMentionCursor(pos);
    });
  }

  const rootClass = ["composer", className].filter(Boolean).join(" ");
  const inputLocked = disabled;
  const sendLocked = sendDisabled ?? disabled;

  return (
    <div className={rootClass}>
      {files.length > 0 && (
        <div className="attachment-bar">
          {files.map((f) => (
            <span key={f.id} className="attachment-chip">
              <PaperclipIcon />
              <span className="attachment-chip-name">{f.file.name}</span>
              <button
                type="button"
                className="attachment-chip__remove"
                onClick={() => onFileRemove(f.id)}
                aria-label="첨부 제거"
              >
                ×
              </button>
            </span>
          ))}
        </div>
      )}

      {modeChip ? (
        <div
          className={[
            "mode-chip",
            modeChipVariant ? `mode-chip--${modeChipVariant}` : undefined,
          ]
            .filter(Boolean)
            .join(" ")}
          role="status"
        >
          <span className="mode-chip__label">
            {modeChipVariant === "discuss" ? <UsersIcon /> : null}
            {modeChipVariant === "plan" ? <ListIcon /> : null}
            {modeChipVariant === "consensus" ? <SparkleIcon /> : null}
            {modeChip}
          </span>
          {modeChipHint ? (
            <span className="mode-chip__hint">{modeChipHint}</span>
          ) : showModeChipHint && isNewSession ? (
            <span className="mode-chip__hint">
              모든 턴 후 plan.md 자동 갱신
            </span>
          ) : showModeChipHint && planAfterSend ? (
            <span className="mode-chip__hint">
              전송 시 plan.md 갱신 (plan 탭에서 끌 수 있음)
            </span>
          ) : null}
        </div>
      ) : null}

      {turnProfile && onTurnProfileChange ? (
        <ComposerTurnPicker
          value={turnProfile}
          onChange={onTurnProfileChange}
          disabled={inputLocked}
          locale={locale}
          hint={turnHint}
          trailing={
            <>
              {onPlanAfterSendChange ? (
                <ComposerPlanToggle
                  checked={planAfterSend}
                  onChange={onPlanAfterSendChange}
                  disabled={inputLocked || planToggleDisabled}
                  label={localeMsg.modePlan}
                  title={
                    planToggleDisabled
                      ? localeMsg.planWorkflowComposerBlocked
                      : localeMsg.modePlanHint
                  }
                />
              ) : null}
            </>
          }
        />
      ) : null}

      {objectionNotice ? (
        <div className="objection-alert" role="alert">
          <span className="objection-alert__icon" aria-hidden>
            <AlertIcon />
          </span>
          <span>{objectionNotice.message}</span>
          {onFocusObjection ? (
            <button
              type="button"
              className="btn btn--danger btn--sm"
              onClick={() =>
                onFocusObjection(
                  objectionNotice.objectionId,
                  objectionNotice.actionIndex,
                )
              }
            >
              {locale === "ko" ? "이의 해결" : "Resolve"}
            </button>
          ) : null}
        </div>
      ) : null}

      {!inputHidden ? (
        <div className="composer-row">
          <div className="composer-capsule">
            {showAttach && (
              <>
                <button
                  type="button"
                  className="btn-attach"
                  disabled={inputLocked}
                  onClick={() => fileInputRef.current?.click()}
                  aria-label="파일 첨부"
                  title="파일 첨부"
                >
                  <PaperclipIcon />
                </button>
                <input
                  ref={fileInputRef}
                  type="file"
                  multiple
                  className="sr-only"
                  onChange={(e) => {
                    if (e.target.files?.length) onFilesAdd(e.target.files);
                    e.target.value = "";
                  }}
                />
              </>
            )}
            <div className="composer-field">
              <SlashCommandMenu
                value={value}
                commands={slashCommands}
                disabled={inputLocked}
                highlightedIndex={slashHighlight}
                onHighlightChange={setSlashHighlight}
                onSelect={(slash) => onChange(slash)}
                onExecute={(cmd) => onSlashExecute?.(cmd)}
              />
              {mentionQuery != null ? (
                <ComposerMentionMenu
                  query={mentionQuery}
                  paths={mentionPaths}
                  loading={mentionLoading}
                  onPick={applyMention}
                />
              ) : null}
              <textarea
                ref={inputRef}
                className="composer-input"
                value={value}
                onChange={(e) => {
                  const nextValue = e.target.value;
                  const nextSlashQuery =
                    nextValue.slice(1).split(/\s/)[0] ?? "";
                  if (nextSlashQuery !== slashQuery) setSlashHighlight(0);
                  onChange(nextValue);
                  setMentionCursor(e.target.selectionStart ?? nextValue.length);
                }}
                onClick={(e) =>
                  setMentionCursor(
                    (e.target as HTMLTextAreaElement).selectionStart ??
                      value.length,
                  )
                }
                placeholder={placeholder}
                disabled={inputLocked}
                rows={1}
                onKeyDown={(e) => {
                  if (value.startsWith("/") && slashFiltered.length > 0) {
                    if (e.key === "ArrowDown") {
                      e.preventDefault();
                      setSlashHighlight(
                        (slashHighlight + 1) % slashFiltered.length,
                      );
                      return;
                    }
                    if (e.key === "ArrowUp") {
                      e.preventDefault();
                      setSlashHighlight(
                        (slashHighlight - 1 + slashFiltered.length) %
                          slashFiltered.length,
                      );
                      return;
                    }
                    if (e.key === "PageDown") {
                      e.preventDefault();
                      setSlashHighlight(
                        Math.min(slashHighlight + 10, slashFiltered.length - 1),
                      );
                      return;
                    }
                    if (e.key === "PageUp") {
                      e.preventDefault();
                      setSlashHighlight(Math.max(slashHighlight - 10, 0));
                      return;
                    }
                    const slashTokenOnly = /^\/\S*$/.test(value);
                    if (
                      (e.key === "Tab" || e.key === "Enter") &&
                      slashTokenOnly &&
                      slashFiltered[slashHighlight]
                    ) {
                      e.preventDefault();
                      const command = slashFiltered[slashHighlight];
                      onChange(command.slash);
                      if (e.key === "Enter") onSlashExecute?.(command);
                      return;
                    }
                  }
                  if (e.key === "Escape" && value.startsWith("/")) {
                    e.preventDefault();
                    onChange("");
                    return;
                  }
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    onSend();
                  }
                }}
              />
              {toolbar && <div className="composer-toolbar">{toolbar}</div>}
            </div>
          </div>
          {running && onStop ? (
            <button
              type="button"
              className="btn-stop"
              onClick={onStop}
              aria-label="답변 중지"
              title="답변 중지"
            >
              <span className="btn-stop__square" aria-hidden />
            </button>
          ) : (
            <button
              type="button"
              className="btn-send"
              disabled={sendLocked || !value.trim()}
              onClick={onSend}
              aria-label="전송"
            >
              <SendIcon />
            </button>
          )}
        </div>
      ) : null}
    </div>
  );
}

function UsersIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      width="13"
      height="13"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.7}
      strokeLinecap="round"
      aria-hidden
    >
      <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
      <circle cx="9" cy="7" r="4" />
      <path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75" />
    </svg>
  );
}

function ListIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      width="13"
      height="13"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.7}
      strokeLinecap="round"
      aria-hidden
    >
      <path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01" />
    </svg>
  );
}

function SparkleIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      width="13"
      height="13"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.7}
      strokeLinecap="round"
      aria-hidden
    >
      <path d="m12 3 1.5 4.5L18 9l-4.5 1.5L12 15l-1.5-4.5L6 9l4.5-1.5L12 3Z" />
    </svg>
  );
}

function SendIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      width="18"
      height="18"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.7}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="M22 2 11 13M22 2l-7 20-4-9-9-4 20-7z" />
    </svg>
  );
}

function AlertIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      width="18"
      height="18"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.7}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="M12 9v4M12 17h.01M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z" />
    </svg>
  );
}

function PaperclipIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.7}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="m16 6-8.5 8.5a2.12 2.12 0 1 0 3 3L19 9a3.12 3.12 0 1 0-4.4-4.4L9.3 14.3a4.62 4.62 0 1 0 6.5 6.5" />
    </svg>
  );
}
