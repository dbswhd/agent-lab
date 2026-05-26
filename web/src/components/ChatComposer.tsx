import { useRef, type ReactNode } from "react";

export type PendingFile = { id: string; file: File };

type Props = {
  value: string;
  onChange: (v: string) => void;
  onSend: () => void;
  disabled?: boolean;
  placeholder?: string;
  files: PendingFile[];
  onFilesAdd: (files: FileList | File[]) => void;
  onFileRemove: (id: string) => void;
  sessionAttachments?: string[];
  showAttach?: boolean;
  toolbar?: ReactNode;
};

export function ChatComposer({
  value,
  onChange,
  onSend,
  disabled,
  placeholder = "메시지",
  files,
  onFilesAdd,
  onFileRemove,
  sessionAttachments = [],
  showAttach = true,
  toolbar,
}: Props) {
  const inputRef = useRef<HTMLInputElement>(null);

  return (
    <footer className="composer">
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
      <div className="composer-row">
        {showAttach && (
          <>
            <button
              type="button"
              className="btn-attach"
              disabled={disabled}
              onClick={() => inputRef.current?.click()}
              aria-label="파일 첨부"
              title="파일 첨부"
            >
              <PaperclipIcon />
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
            value={value}
            onChange={(e) => onChange(e.target.value)}
            placeholder={placeholder}
            disabled={disabled}
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
        <button
          type="button"
          className="btn-send"
          disabled={disabled || !value.trim()}
          onClick={onSend}
          aria-label="전송"
        >
          ↑
        </button>
      </div>
    </footer>
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
