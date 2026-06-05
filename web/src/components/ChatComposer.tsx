import { useMemo, useRef, useState, type ReactNode } from "react";
import { CollapsibleGlassPanel } from "./CollapsibleGlassPanel";
import { ComposerPlanToggle } from "./ComposerPlanToggle";
import { ComposerEfficiencyToggle } from "./ComposerEfficiencyToggle";
import { ComposerTurnPicker } from "./ComposerTurnPicker";
import { SlashCommandMenu } from "./SlashCommandMenu";
import type { SlashCommandRecord } from "../api/client";
import type { ComposerTurnProfile } from "../utils/turnProfile";

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
  sessionAttachments?: string[];
  showAttach?: boolean;
  toolbar?: ReactNode;
  className?: string;
  turnProfile?: ComposerTurnProfile;
  onTurnProfileChange?: (profile: ComposerTurnProfile) => void;
  planAfterSend?: boolean;
  onPlanAfterSendChange?: (on: boolean) => void;
  executeDisabled?: boolean;
  pendingExecuteCount?: number;
  efficiencyOn?: boolean;
  onEfficiencyChange?: (on: boolean) => void;
  /** plan이 토론보다 뒤처짐 — composer 위 안내 */
  planStaleNotice?: string | null;
  objectionNotice?: ObjectionNotice | null;
  onFocusObjection?: (objectionId: string, actionIndex?: number) => void;
  turnCostHint?: string | null;
  fullTeamConfirm?: {
    required: boolean;
    checked: boolean;
    label: string;
    detail?: string;
    disabled?: boolean;
    onChange: (checked: boolean) => void;
  } | null;
  /** Hide textarea/send (mode picker stays visible). */
  inputHidden?: boolean;
  /** Show 「정리」 toggle beside turn picker (default: plan tab only). */
  showPlanToggle?: boolean;
  /** Secondary line under mode chip (off = less plan noise on chat). */
  showModeChipHint?: boolean;
  running?: boolean;
  onStop?: () => void;
  /** Current room turn mode (토론 / 정리 / 합의). */
  modeChip?: string | null;
  modeChipVariant?: "discuss" | "plan" | "consensus";
  /** New session — plan scribe timing hint. */
  isNewSession?: boolean;
  slashCommands?: SlashCommandRecord[];
  onSlashExecute?: (command: SlashCommandRecord) => void;
};

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
  sessionAttachments = [],
  showAttach = true,
  toolbar,
  className,
  turnProfile,
  onTurnProfileChange,
  planAfterSend = false,
  onPlanAfterSendChange,
  executeDisabled: _executeDisabled,
  pendingExecuteCount: _pendingExecuteCount,
  efficiencyOn = false,
  onEfficiencyChange,
  planStaleNotice,
  objectionNotice,
  onFocusObjection,
  turnCostHint,
  fullTeamConfirm,
  inputHidden = false,
  showPlanToggle = false,
  showModeChipHint = false,
  running = false,
  onStop,
  modeChip,
  modeChipVariant,
  isNewSession = false,
  slashCommands = [],
  onSlashExecute,
}: Props) {
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [slashHighlight, setSlashHighlight] = useState(0);

  const slashFiltered = useMemo(() => {
    if (!value.startsWith("/")) return [];
    const query = value.slice(1).split(/\s/)[0]?.toLowerCase() ?? "";
    const rows = slashCommands.filter((c) => c.enabled !== false);
    if (!query) return rows;
    return rows.filter(
      (c) =>
        c.slash.toLowerCase().includes(query) ||
        c.label.toLowerCase().includes(query),
    );
  }, [slashCommands, value]);

  const rootClass = ["composer", className].filter(Boolean).join(" ");
  const inputLocked = disabled;
  const sendLocked = sendDisabled ?? disabled;

  return (
    <div className={rootClass}>
      {(files.length > 0 || sessionAttachments.length > 0) && (
        <div className="attachment-bar">
          {sessionAttachments.map((name) => (
            <span key={`s-${name}`} className="attachment-chip attachment-chip--saved">
              <span className="attachment-chip-icon" aria-hidden>
                <PaperclipIcon />
              </span>
              <span className="attachment-chip-name">{name}</span>
            </span>
          ))}
          {files.map((f) => (
            <span key={f.id} className="attachment-chip">
              <span className="attachment-chip-icon" aria-hidden>
                <PaperclipIcon />
              </span>
              <span className="attachment-chip-name">{f.file.name}</span>
              <button
                type="button"
                className="attachment-chip-remove"
                onClick={() => onFileRemove(f.id)}
                aria-label="첨부 제거"
              >
                ×
              </button>
            </span>
          ))}
        </div>
      )}
      <div className="composer-dock">
        {modeChip ? (
          <p
            className={[
              "composer-mode-chip",
              modeChipVariant
                ? `composer-mode-chip--${modeChipVariant}`
                : undefined,
            ]
              .filter(Boolean)
              .join(" ")}
            role="status"
          >
            <span className="composer-mode-chip__label">{modeChip}</span>
            {showModeChipHint && isNewSession ? (
              <span className="composer-mode-chip__hint">
                첫 전송은 토론만 · plan 갱신은 plan 탭
              </span>
            ) : showModeChipHint && planAfterSend ? (
              <span className="composer-mode-chip__hint">
                전송 시 plan.md 갱신 (plan 탭에서 끌 수 있음)
              </span>
            ) : null}
          </p>
        ) : null}
        {turnProfile && onTurnProfileChange ? (
          <div className="composer-turn-row">
            <ComposerTurnPicker
              value={turnProfile}
              onChange={onTurnProfileChange}
              disabled={inputLocked}
              costHint={turnCostHint}
              trailing={
                <>
                  {showPlanToggle && onPlanAfterSendChange ? (
                    <ComposerPlanToggle
                      checked={planAfterSend}
                      onChange={onPlanAfterSendChange}
                      disabled={inputLocked}
                    />
                  ) : null}
                  {onEfficiencyChange ? (
                    <ComposerEfficiencyToggle
                      checked={efficiencyOn}
                      onChange={onEfficiencyChange}
                      disabled={inputLocked}
                    />
                  ) : null}
                </>
              }
            />
          </div>
        ) : null}
        {fullTeamConfirm?.required ? (
          <div
            className={[
              "composer-cost-hint",
              "composer-cost-hint--confirm",
              fullTeamConfirm?.checked ? "is-confirmed" : undefined,
            ]
              .filter(Boolean)
              .join(" ")}
            role="alert"
          >
            <label className="composer-cost-hint__confirm">
              <input
                className="mac-checkbox"
                type="checkbox"
                checked={fullTeamConfirm.checked}
                disabled={fullTeamConfirm.disabled}
                onChange={(e) => fullTeamConfirm.onChange(e.target.checked)}
              />
              <span>{fullTeamConfirm.label}</span>
            </label>
            {fullTeamConfirm.detail ? (
              <span className="composer-cost-hint__detail">
                {fullTeamConfirm.detail}
              </span>
            ) : null}
          </div>
        ) : null}
        {planStaleNotice ? (
          <CollapsibleGlassPanel
            className="composer-alert-panel"
            title="plan 알림"
            summary={planStaleNotice}
            variant="warn"
            defaultOpen={false}
          >
            <p className="composer-alert-panel__text">{planStaleNotice}</p>
          </CollapsibleGlassPanel>
        ) : null}
        {objectionNotice ? (
          <div className="composer-objection-alert" role="alert">
            <span>{objectionNotice.message}</span>
            {onFocusObjection ? (
              <button
                type="button"
                className="room-plan-btn"
                onClick={() =>
                  onFocusObjection(
                    objectionNotice.objectionId,
                    objectionNotice.actionIndex,
                  )
                }
              >
                이의 해결
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
                  <PlusIcon />
                </button>
                <input
                  ref={fileInputRef}
                  type="file"
                  multiple
                  className="composer-file-input"
                  onChange={(e) => {
                    if (e.target.files?.length) onFilesAdd(e.target.files);
                    e.target.value = "";
                  }}
                />
              </>
            )}
            <div className="composer-field composer-field--slash">
              <SlashCommandMenu
                value={value}
                commands={slashCommands}
                disabled={inputLocked}
                onSelect={(slash) => onChange(slash)}
                onExecute={(cmd) => onSlashExecute?.(cmd)}
              />
              <textarea
                ref={inputRef}
                className="mac-textfield mac-textfield--multiline composer-input"
                value={value}
                onChange={(e) => onChange(e.target.value)}
                placeholder={placeholder}
                disabled={inputLocked}
                rows={1}
                onKeyDown={(e) => {
                  if (value.startsWith("/") && slashFiltered.length > 0) {
                    if (e.key === "ArrowDown") {
                      e.preventDefault();
                      setSlashHighlight((slashHighlight + 1) % slashFiltered.length);
                      return;
                    }
                    if (e.key === "ArrowUp") {
                      e.preventDefault();
                      setSlashHighlight(
                        (slashHighlight - 1 + slashFiltered.length) % slashFiltered.length,
                      );
                      return;
                    }
                    if (e.key === "Tab" && slashFiltered[slashHighlight]) {
                      e.preventDefault();
                      onChange(slashFiltered[slashHighlight].slash);
                      return;
                    }
                  }
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    onSend();
                  }
                }}
              />
              {toolbar && <div className="composer-toolbar">{toolbar}</div>}
            </div>
            {running && onStop ? (
              <button
                type="button"
                className="btn-stop-reply"
                onClick={onStop}
                aria-label="답변 중지"
                title="답변 중지"
              >
                <span className="btn-stop-reply__square" aria-hidden />
              </button>
            ) : null}
          </div>
          <button
            type="button"
            className="btn-send btn-send--composer"
            disabled={sendLocked || !value.trim()}
            onClick={onSend}
            aria-label="전송"
          >
            ↑
          </button>
        </div>
        ) : null}
      </div>
    </div>
  );
}

function PlusIcon() {
  return (
    <svg
      className="icon-plus"
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      aria-hidden
    >
      <line x1="8" y1="4" x2="8" y2="12" />
      <line x1="4" y1="8" x2="12" y2="8" />
    </svg>
  );
}

function PaperclipIcon() {
  return (
    <svg
      className="icon-paperclip"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="m16 6-8.5 8.5a2.12 2.12 0 1 0 3 3L19 9a3.12 3.12 0 1 0-4.4-4.4L9.3 14.3a4.62 4.62 0 1 0 6.5 6.5" />
    </svg>
  );
}
