import { useMemo, useRef, useState, useEffect, type ReactNode } from "react";
import {
  ComposerMentionMenu,
  type MentionMenuOption,
} from "./ComposerMentionMenu";
import { ComposerAgentStack } from "./ComposerAgentStack";
import { formatAgentModelName } from "../utils/roomModels";
import {
  mentionQueryAtCursor,
  useComposerMentionPaths,
} from "../hooks/useComposerMentionPaths";
import { buildComposerHighlightNodes } from "../utils/composerInputHighlight";
import { bestSlashHighlightIndex } from "../utils/slashCommandMenuGroups";
import { SlashCommandMenu } from "./SlashCommandMenu";
import type { SlashCommandRecord } from "../api/client";
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
  /** When busy, allow mid-run steer instead of a full Room send. */
  steerEligible?: boolean;
  onSteer?: () => void;
  steerBusy?: boolean;
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
  /** Floating slash-command choice popover (login / logout / scope). */
  choicePopover?: ReactNode;
  /** OAuth CLI progress or API-key entry — anchored in composer field. */
  authPopover?: ReactNode;
  /** /login · /logout agent picker — anchored like model popover. */
  authPickerPopover?: ReactNode;
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
  executeDisabled: _executeDisabled,
  pendingExecuteCount: _pendingExecuteCount,
  objectionNotice,
  onFocusObjection,
  turnHint,
  costHint: _costHint,
  locale = "en",
  inputHidden = false,
  showModeChipHint = false,
  modeChipHint,
  running = false,
  onStop,
  steerEligible = false,
  onSteer,
  steerBusy = false,
  modeChip,
  modeChipVariant,
  isNewSession = false,
  slashCommands = [],
  onSlashExecute: _onSlashExecute,
  sessionId = null,
  activeModels = [],
  onOpenModelPicker,
  choicePopover,
  authPopover,
  authPickerPopover,
  modelPopover,
}: Props) {
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const mirrorRef = useRef<HTMLDivElement>(null);
  const composerCapsuleRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [slashHighlight, setSlashHighlight] = useState(0);
  const [mentionHighlight, setMentionHighlight] = useState(0);
  const [mentionVisibleOptions, setMentionVisibleOptions] = useState<
    MentionMenuOption[]
  >([]);
  const [slashVisibleCommands, setSlashVisibleCommands] = useState<
    SlashCommandRecord[]
  >([]);
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
    syncInputMirrorScroll();
  }, [value]);

  const slashQuery = value.slice(1).split(/\s/)[0] ?? "";

  useEffect(() => {
    setSlashHighlight(
      bestSlashHighlightIndex(slashVisibleCommands, slashQuery),
    );
  }, [slashQuery, slashVisibleCommands]);

  const highlightNodes = useMemo(
    () => buildComposerHighlightNodes(value),
    [value],
  );

  function syncInputMirrorScroll() {
    const input = inputRef.current;
    const mirror = mirrorRef.current;
    if (!input || !mirror) return;
    mirror.scrollTop = input.scrollTop;
    mirror.scrollLeft = input.scrollLeft;
  }

  const mentionQuery = useMemo(() => {
    if (!sessionId) return null;
    return mentionQueryAtCursor(value, mentionCursor);
  }, [sessionId, value, mentionCursor]);

  useEffect(() => {
    if (mentionQuery != null) void ensureLoaded();
  }, [mentionQuery, ensureLoaded]);

  useEffect(() => {
    if (mentionQuery != null) setMentionHighlight(0);
  }, [mentionQuery]);

  useEffect(() => {
    if (mentionVisibleOptions.length === 0) {
      setMentionHighlight(0);
      return;
    }
    if (mentionHighlight >= mentionVisibleOptions.length) {
      setMentionHighlight(mentionVisibleOptions.length - 1);
    }
  }, [mentionHighlight, mentionVisibleOptions.length]);

  function focusInputAt(pos: number) {
    requestAnimationFrame(() => {
      const next = inputRef.current;
      if (!next) return;
      next.focus();
      next.setSelectionRange(pos, pos);
      setMentionCursor(pos);
    });
  }

  function applyMention(token: string) {
    const el = inputRef.current;
    const cursor = el?.selectionStart ?? value.length;
    const head = value.slice(0, cursor);
    const tail = value.slice(cursor);
    const replaced = head.replace(/(?<![A-Za-z0-9_-])@([^\s@]*)$/, (m) =>
      m.startsWith("@") ? `@${token} ` : ` @${token} `,
    );
    onChange(`${replaced}${tail}`);
    focusInputAt(replaced.length);
  }

  const rootClass = ["composer", className].filter(Boolean).join(" ");
  const inputLocked = disabled;
  const sendLocked = sendDisabled ?? disabled;
  const primaryModel = activeModels[0] ?? null;
  const hiddenModelCount = Math.max(activeModels.length - 1, 0);
  const resolvedModeChipHint = resolveModeChipHint({
    modeChipHint,
    showModeChipHint,
    isNewSession,
    modeChipVariant,
  });
  const ModeChipIcon = modeChipVariant
    ? MODE_CHIP_ICONS[modeChipVariant]
    : null;

  function openMentionStart() {
    if (inputLocked) return;
    const needsSpace = value.length > 0 && !/\s$/.test(value);
    const nextValue = `${value}${needsSpace ? " " : ""}@`;
    onChange(nextValue);
    if (sessionId) void ensureLoaded();
    focusInputAt(nextValue.length);
  }

  function openSlashStart() {
    if (inputLocked) return;
    const nextValue = value.trim().length === 0 ? "/" : `${value} /`;
    onChange(nextValue);
    focusInputAt(nextValue.length);
  }

  const presetControls =
    activeModels.length > 0 ? (
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
            {ModeChipIcon ? <ModeChipIcon /> : null}
            {modeChip}
          </span>
          {resolvedModeChipHint ? (
            <span className="mode-chip__hint">{resolvedModeChipHint}</span>
          ) : null}
        </div>
      ) : null}

      {turnHint ? (
        <p className="composer-hint" role="status">
          {turnHint}
        </p>
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
            {authPickerPopover}
            <div className="composer-content">
              <div className="composer-field">
                {authPopover}
                {choicePopover}
                <SlashCommandMenu
                  value={value}
                  commands={slashCommands}
                  disabled={inputLocked}
                  highlightedIndex={slashHighlight}
                  onHighlightChange={setSlashHighlight}
                  onSelect={(slash) => onChange(slash)}
                  insideRef={composerCapsuleRef}
                  onVisibleCommandsChange={setSlashVisibleCommands}
                  onDismiss={() => {
                    if (value.startsWith("/")) onChange("");
                  }}
                />
                {mentionQuery != null ? (
                  <ComposerMentionMenu
                    query={mentionQuery}
                    paths={mentionPaths}
                    agents={activeModels}
                    loading={mentionLoading}
                    onPickPath={applyMention}
                    onPickAgent={applyMention}
                    highlightedIndex={mentionHighlight}
                    onHighlightChange={setMentionHighlight}
                    onOptionsChange={setMentionVisibleOptions}
                  />
                ) : null}
                <div className="composer-input-stack">
                  <div
                    ref={mirrorRef}
                    className="composer-input-mirror"
                    aria-hidden="true"
                  >
                    {highlightNodes}
                  </div>
                  <textarea
                    ref={inputRef}
                    className="composer-input composer-input--overlay"
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
                    onScroll={syncInputMirrorScroll}
                    onClick={(e) => {
                      setMentionCursor(
                        (e.target as HTMLTextAreaElement).selectionStart ??
                          value.length,
                      );
                      syncInputMirrorScroll();
                    }}
                    placeholder={placeholder}
                    disabled={inputLocked}
                    rows={1}
                    onKeyDown={(e) => {
                      if (
                        mentionQuery != null &&
                        mentionVisibleOptions.length > 0
                      ) {
                        if (e.key === "ArrowDown") {
                          e.preventDefault();
                          setMentionHighlight((h) =>
                            cycleMenuIndex(h, mentionVisibleOptions.length, 1),
                          );
                          return;
                        }
                        if (e.key === "ArrowUp") {
                          e.preventDefault();
                          setMentionHighlight((h) =>
                            cycleMenuIndex(h, mentionVisibleOptions.length, -1),
                          );
                          return;
                        }
                        if (e.key === "Tab" || e.key === "Enter") {
                          e.preventDefault();
                          const option =
                            mentionVisibleOptions[mentionHighlight];
                          if (option) applyMention(option.token);
                          return;
                        }
                      }
                      if (
                        value.startsWith("/") &&
                        slashVisibleCommands.length > 0
                      ) {
                        if (e.key === "ArrowDown") {
                          e.preventDefault();
                          setSlashHighlight((h) =>
                            cycleMenuIndex(h, slashVisibleCommands.length, 1),
                          );
                          return;
                        }
                        if (e.key === "ArrowUp") {
                          e.preventDefault();
                          setSlashHighlight((h) =>
                            cycleMenuIndex(h, slashVisibleCommands.length, -1),
                          );
                          return;
                        }
                        if (e.key === "PageDown") {
                          e.preventDefault();
                          setSlashHighlight(
                            Math.min(
                              slashHighlight + 10,
                              slashVisibleCommands.length - 1,
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
                          slashVisibleCommands[slashHighlight]
                        ) {
                          e.preventDefault();
                          const command = slashVisibleCommands[slashHighlight];
                          onChange(command.slash);
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
                </div>
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
                  disabled={inputLocked}
                  onClick={openMentionStart}
                  aria-label="멘션"
                  title="에이전트 또는 파일 멘션 (@)"
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
                      <span className="composer-model-select__sep" aria-hidden>
                        ·
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
                  <>
                    {steerEligible && onSteer ? (
                      <button
                        type="button"
                        className="btn-send btn-send--steer"
                        disabled={steerBusy || !value.trim()}
                        onClick={onSteer}
                        aria-label="Steer"
                        title={
                          locale === "ko"
                            ? "실행 중 지시 (다음 에이전트 단계에 반영)"
                            : "Steer while running (applied at next agent step)"
                        }
                        data-testid="composer-steer"
                      >
                        Steer
                      </button>
                    ) : null}
                    <button
                      type="button"
                      className="btn-stop"
                      onClick={onStop}
                      aria-label="답변 중지"
                      title="답변 중지"
                    >
                      <span className="btn-stop__square" aria-hidden />
                    </button>
                  </>
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

function cycleMenuIndex(
  current: number,
  length: number,
  delta: number,
): number {
  return (current + delta + length) % length;
}

const MODE_CHIP_ICONS = {
  discuss: UsersIcon,
  plan: ListIcon,
  consensus: SparkleIcon,
} as const;

function resolveModeChipHint(opts: {
  modeChipHint?: string | null;
  showModeChipHint: boolean;
  isNewSession: boolean;
  modeChipVariant?: "discuss" | "plan" | "consensus";
}): string | null {
  if (opts.modeChipHint) return opts.modeChipHint;
  if (!opts.showModeChipHint) return null;
  if (opts.isNewSession) return "모든 턴 후 plan.md 자동 갱신";
  if (opts.modeChipVariant === "plan") {
    return "Supervisor — plan.md는 TurnPolicy로 갱신";
  }
  return null;
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
