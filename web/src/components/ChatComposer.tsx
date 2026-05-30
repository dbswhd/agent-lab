import { useRef, type ReactNode } from "react";
import { CollapsibleGlassPanel } from "./CollapsibleGlassPanel";
import { ComposerEfficiencyToggle } from "./ComposerEfficiencyToggle";
import { ComposerTurnPicker } from "./ComposerTurnPicker";
import type { ComposerTurnProfile } from "../utils/turnProfile";

export type PendingFile = { id: string; file: File };

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
  efficiencyOn?: boolean;
  onEfficiencyChange?: (on: boolean) => void;
  /** plan이 토론보다 뒤처짐 — composer 위 안내 */
  planStaleNotice?: string | null;
  running?: boolean;
  onStop?: () => void;
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
  efficiencyOn = false,
  onEfficiencyChange,
  planStaleNotice,
  running = false,
  onStop,
}: Props) {
  const inputRef = useRef<HTMLInputElement>(null);

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
        {turnProfile && onTurnProfileChange ? (
          <div className="composer-turn-row">
            <ComposerTurnPicker
              value={turnProfile}
              onChange={onTurnProfileChange}
              disabled={inputLocked}
              trailing={
                onEfficiencyChange ? (
                  <ComposerEfficiencyToggle
                    checked={efficiencyOn}
                    onChange={onEfficiencyChange}
                    disabled={inputLocked}
                  />
                ) : null
              }
            />
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
        <div className="composer-row">
          <div className="composer-capsule">
            {showAttach && (
              <>
                <button
                  type="button"
                  className="btn-attach"
                  disabled={inputLocked}
                  onClick={() => inputRef.current?.click()}
                  aria-label="파일 첨부"
                  title="파일 첨부"
                >
                  <PlusIcon />
                </button>
                <input
                  ref={inputRef}
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
            <div className="composer-field">
              <textarea
                className="mac-textfield mac-textfield--multiline composer-input"
                value={value}
                onChange={(e) => onChange(e.target.value)}
                placeholder={placeholder}
                disabled={inputLocked}
                rows={1}
                onKeyDown={(e) => {
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
