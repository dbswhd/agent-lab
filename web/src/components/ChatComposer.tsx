import { useMemo, useRef, useState, useEffect, type ReactNode } from "react";
import { ComposerMentionMenu } from "./ComposerMentionMenu";
import { ComposerAgentStack } from "./ComposerAgentStack";
import { presetDisplayLabel, presetHintLine } from "../utils/roomPresets";
import { formatAgentModelName } from "../utils/roomModels";
import {
  mentionQueryAtCursor,
  useComposerMentionPaths,
} from "../hooks/useComposerMentionPaths";
import { SlashCommandMenu } from "./SlashCommandMenu";
import type { SlashCommandRecord, RoomPreset } from "../api/client";
import type { ComposerTurnProfile } from "../utils/turnProfile";
import type { Locale } from "../i18n/locale";

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
  /** @deprecated Runtime turn profile only — UI uses room presets (fast / supervisor). */
  turnProfile?: ComposerTurnProfile;
  /** @deprecated Use room presets instead of quick / team / loop picker. */
  onTurnProfileChange?: (profile: ComposerTurnProfile) => void;
  executeDisabled?: boolean;
  pendingExecuteCount?: number;
  /** @deprecated Plan stale notices live on the Work tab. */
  planStaleNotice?: string | null;
  objectionNotice?: ObjectionNotice | null;
  onFocusObjection?: (objectionId: string, actionIndex?: number) => void;
  /** When set, replaces joined description + costHint (prototype one-liner). */
  turnHint?: string | null;
  /** Cost / loop ceiling line (shown after preset description). */
  costHint?: string | null;
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
  activeModels?: readonly {
    id: string;
    label: string;
    model?: string | null;
    ready?: boolean;
  }[];
  onOpenModelPicker?: () => void;
  /** Room preset (fast / supervisor) — primary composer mode control. */
  roomPresets?: RoomPreset[];
  roomPreset?: string | null;
  onRoomPresetSelect?: (id: string) => void;
  /** Floating slash-command choice popover (login / logout / scope). */
  choicePopover?: ReactNode;
  /** /model picker — anchored to the model button. */
  modelPopover?: ReactNode;
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
  turnProfile: _turnProfile,
  onTurnProfileChange: _onTurnProfileChange,
  executeDisabled: _executeDisabled,
  pendingExecuteCount: _pendingExecuteCount,
  objectionNotice,
  onFocusObjection,
  turnHint: _turnHint,
  costHint: _costHint,
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
  activeModels = [],
  onOpenModelPicker,
  roomPresets,
  roomPreset = null,
  onRoomPresetSelect,
  choicePopover,
  modelPopover,
}: Props) {
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const composerCapsuleRef = useRef<HTMLDivElement>(null);
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
  const primaryModel = activeModels[0] ?? null;
  const hiddenModelCount = Math.max(activeModels.length - 1, 0);

  function openMentionStart() {
    if (inputLocked || !sessionId) return;
    const needsSpace = value.length > 0 && !/\s$/.test(value);
    const nextValue = `${value}${needsSpace ? " " : ""}@`;
    onChange(nextValue);
    void ensureLoaded();
    requestAnimationFrame(() => {
      const next = inputRef.current;
      if (!next) return;
      next.focus();
      const pos = nextValue.length;
      next.setSelectionRange(pos, pos);
      setMentionCursor(pos);
    });
  }

  function openSlashStart() {
    if (inputLocked) return;
    const nextValue = value.trim().length === 0 ? "/" : `${value} /`;
    onChange(nextValue);
    requestAnimationFrame(() => {
      const next = inputRef.current;
      if (!next) return;
      next.focus();
      const pos = nextValue.length;
      next.setSelectionRange(pos, pos);
      setMentionCursor(pos);
    });
  }

  const presetControls =
    roomPresets && roomPresets.length > 0 && onRoomPresetSelect ? (
      <div
        className="composer-prompt-head"
        role="radiogroup"
        aria-label={locale === "ko" ? "Room 프리셋" : "Room preset"}
      >
        <div className="composer-prompt-head__row">
          <ComposerAgentStack agents={activeModels} max={4} size={32} />
          <div className="turn-seg composer-preset-seg composer-preset-seg--end">
            {roomPresets.map((p) => (
              <button
                key={p.id}
                type="button"
                role="radio"
                aria-checked={roomPreset === p.id}
                className={roomPreset === p.id ? "is-active" : ""}
                data-preset={p.id}
                disabled={inputLocked}
                title={presetHintLine(p, locale) ?? p.description}
                onClick={() => onRoomPresetSelect(p.id)}
              >
                {presetDisplayLabel(p, locale)}
              </button>
            ))}
          </div>
        </div>
      </div>
    ) : activeModels.length > 0 ? (
      <div className="composer-prompt-head">
        <ComposerAgentStack agents={activeModels} max={4} size={32} />
      </div>
    ) : null;

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
          ) : showModeChipHint && modeChipVariant === "plan" ? (
            <span className="mode-chip__hint">
              Supervisor — plan.md는 TurnPolicy로 갱신
            </span>
          ) : null}
        </div>
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
        <div
          className={[
            "composer-row",
            presetControls ? "composer-row--stacked" : undefined,
          ]
            .filter(Boolean)
            .join(" ")}
        >
          {presetControls ? (
            <div className="composer-prompt-status">{presetControls}</div>
          ) : null}
          <div
            ref={composerCapsuleRef}
            className={[
              "composer-capsule",
              presetControls ? "composer-capsule--stacked" : undefined,
            ]
              .filter(Boolean)
              .join(" ")}
          >
            {modelPopover}
            <div className="composer-content">
              <div className="composer-field">
                {choicePopover}
                <SlashCommandMenu
                  value={value}
                  commands={slashCommands}
                  disabled={inputLocked}
                  highlightedIndex={slashHighlight}
                  onHighlightChange={setSlashHighlight}
                  onSelect={(slash) => onChange(slash)}
                  onExecute={(cmd) => onSlashExecute?.(cmd)}
                  insideRef={composerCapsuleRef}
                  onDismiss={() => {
                    if (value.startsWith("/")) onChange("");
                  }}
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
                    setMentionCursor(
                      e.target.selectionStart ?? nextValue.length,
                    );
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
                          Math.min(
                            slashHighlight + 10,
                            slashFiltered.length - 1,
                          ),
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
            <div className="composer-action-row">
              <div className="composer-action-row__start">
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
                <button
                  type="button"
                  className="btn-attach"
                  disabled={inputLocked || !sessionId}
                  onClick={openMentionStart}
                  aria-label="파일 멘션"
                  title="파일 멘션"
                >
                  <AtIcon />
                </button>
                <button
                  type="button"
                  className="composer-command-shortcut"
                  disabled={inputLocked}
                  onClick={openSlashStart}
                  aria-label="Slash command"
                  title="Slash command"
                >
                  <span className="shortcut-key">/</span>
                  <span>commands</span>
                </button>
              </div>
              <div className="composer-action-row__end">
                {primaryModel ? (
                  <div className="composer-model-select-wrap">
                    <button
                      type="button"
                      className="composer-model-select"
                      onClick={onOpenModelPicker}
                      disabled={!onOpenModelPicker}
                      title={`${primaryModel.label} · ${formatAgentModelName(
                        primaryModel.model,
                        primaryModel.id,
                      )}`}
                    >
                      <span className="composer-model-select__agent">
                        {primaryModel.label}
                      </span>
                      <strong>
                        {formatAgentModelName(
                          primaryModel.model,
                          primaryModel.id,
                        )}
                      </strong>
                      {hiddenModelCount > 0 ? (
                        <span className="composer-model-select__more">
                          +{hiddenModelCount}
                        </span>
                      ) : null}
                      <span
                        className="composer-model-select__chevron"
                        aria-hidden
                      >
                        ▾
                      </span>
                    </button>
                  </div>
                ) : null}
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
            </div>
          </div>
        </div>
      ) : presetControls ? (
        <div className="composer-row composer-row--stacked">
          <div className="composer-prompt-status">{presetControls}</div>
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
      width="20"
      height="20"
      fill="none"
      stroke="currentColor"
      strokeWidth={2.5}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="M12 19V5M5 12l7-7 7 7" />
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
      width="20"
      height="20"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48" />
    </svg>
  );
}

function AtIcon() {
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
      <circle cx="12" cy="12" r="4" />
      <path d="M16 8v5a3 3 0 0 0 6 0v-1a10 10 0 1 0-4 8" />
    </svg>
  );
}
