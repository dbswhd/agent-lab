import type { WorkspacePreset } from "../utils/sessionSetup";
import { CUSTOM_WORKSPACE_ID } from "../utils/sessionSetup";

type Props = {
  workspaces: WorkspacePreset[];
  workspaceId: string;
  workspacePath: string | null;
  onWorkspaceChange: (id: string, path?: string | null) => void;
  onBrowseFolder: () => void;
  researchMode?: boolean;
  onResearchModeChange?: (on: boolean) => void;
  disabled?: boolean;
  compact?: boolean;
};

function FolderIcon() {
  return (
    <svg
      className="session-setup-bar__folder-icon"
      width="18"
      height="18"
      viewBox="0 0 18 18"
      aria-hidden
    >
      <path
        fill="currentColor"
        d="M2 4.5A1.5 1.5 0 0 1 3.5 3h3.09a1 1 0 0 1 .708.293L8.293 4.5H14.5A1.5 1.5 0 0 1 16 6v7.5a1.5 1.5 0 0 1-1.5 1.5h-11A1.5 1.5 0 0 1 2 13.5v-9Z"
        opacity="0.92"
      />
    </svg>
  );
}

function shortenPath(path: string, max = 56): string {
  const trimmed = path.trim();
  if (trimmed.length <= max) return trimmed;
  const parts = trimmed.split(/[/\\]/).filter(Boolean);
  if (parts.length <= 2) {
    return `…${trimmed.slice(-(max - 1))}`;
  }
  const tail = parts.slice(-2).join("/");
  return `…/${tail}`;
}

export function SessionSetupBar({
  workspaces,
  workspaceId,
  workspacePath,
  onWorkspaceChange,
  onBrowseFolder,
  researchMode = false,
  onResearchModeChange,
  disabled,
  compact = false,
}: Props) {
  const isCustom = workspaceId === CUSTOM_WORKSPACE_ID;
  const preset =
    workspaces.find((w) => w.id === workspaceId) ??
    (isCustom ? null : workspaces.find((w) => w.available) ?? workspaces[0]);
  const displayPath = isCustom ? workspacePath : preset?.path ?? null;
  const selectValue = isCustom
    ? CUSTOM_WORKSPACE_ID
    : preset?.id ?? workspaceId;
  const activeLabel = isCustom
    ? workspacePath
      ? "선택한 폴더"
      : "폴더를 선택하세요"
    : preset?.label ?? "작업 폴더";

  return (
    <div
      className={[
        "session-setup-bar",
        compact ? "session-setup-bar--compact" : undefined,
        isCustom && !workspacePath ? "session-setup-bar--needs-path" : undefined,
      ]
        .filter(Boolean)
        .join(" ")}
    >
      <div className="session-setup-bar__card">
        <div className="session-setup-bar__head">
          <span className="session-setup-bar__icon-wrap" aria-hidden>
            <FolderIcon />
          </span>
          <div className="session-setup-bar__intro">
            <span className="session-setup-bar__label">작업 폴더</span>
            <span className="session-setup-bar__active">{activeLabel}</span>
          </div>
        </div>

        <div className="session-setup-bar__controls">
          <select
            className="mac-popup session-setup-bar__select"
            value={selectValue}
            disabled={disabled || workspaces.length === 0}
            onChange={(e) => {
              const next = e.target.value;
              if (next === CUSTOM_WORKSPACE_ID) {
                onBrowseFolder();
                return;
              }
              onWorkspaceChange(next, null);
            }}
            aria-label="작업 폴더 프리셋"
          >
            {workspaces.map((w) => (
              <option key={w.id} value={w.id} disabled={!w.available}>
                {w.label}
                {!w.available ? " (사용 불가)" : ""}
              </option>
            ))}
            <option value={CUSTOM_WORKSPACE_ID}>다른 폴더…</option>
          </select>
          <button
            type="button"
            className="mac-btn-secondary session-setup-bar__browse"
            disabled={disabled}
            onClick={onBrowseFolder}
          >
            폴더 선택…
          </button>
        </div>

        {!compact && displayPath ? (
          <p className="session-setup-bar__path" title={displayPath}>
            {shortenPath(displayPath)}
          </p>
        ) : null}

        {!compact && isCustom && !workspacePath ? (
          <p className="session-setup-bar__hint">
            에이전트가 읽고 수정할 프로젝트 루트 폴더를 선택하세요.
          </p>
        ) : null}

        {onResearchModeChange ? (
          <label
            className="session-setup-bar__research"
            title="Codex/Claude 산출을 artifacts[]에 저장 · 분업 턴과 함께 사용"
          >
            <input
              type="checkbox"
              className="session-setup-bar__research-input"
              checked={researchMode}
              disabled={disabled}
              onChange={(e) => onResearchModeChange(e.target.checked)}
            />
            <span>연구·분업 (artifacts 수집)</span>
          </label>
        ) : null}
      </div>
    </div>
  );
}
