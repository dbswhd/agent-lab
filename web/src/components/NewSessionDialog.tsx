import { useCallback, useEffect, useRef, useState } from "react";
import { fetchSessionSetupOptions } from "../api/client";
import { pickWorkspaceFolder } from "../utils/pickWorkspaceFolder";
import {
  CUSTOM_WORKSPACE_ID,
  getStoredWorkspaceId,
  getStoredWorkspacePath,
  setStoredWorkspaceId,
  setStoredWorkspacePath,
  type SessionSetupOptions,
  type WorkspacePreset,
} from "../utils/sessionSetup";

export type NewSessionParams = {
  readonly workspaceId: string;
  readonly workspacePath: string | null;
  readonly topic?: string | null;
};

type Props = {
  readonly open: boolean;
  readonly initialTopic?: string | null;
  readonly onClose: () => void;
  readonly onCreate: (params: NewSessionParams) => void;
};

export function NewSessionDialog({
  open,
  initialTopic = null,
  onClose,
  onCreate,
}: Props) {
  const [setupOptions, setSetupOptions] = useState<SessionSetupOptions | null>(
    null,
  );
  const [loadError, setLoadError] = useState(false);
  const [workspaceId, setWorkspaceId] = useState(getStoredWorkspaceId);
  const [workspacePath, setWorkspacePath] = useState<string | null>(
    getStoredWorkspacePath,
  );
  const firstChoiceRef = useRef<HTMLButtonElement>(null);
  const modalRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    setLoadError(false);
    void fetchSessionSetupOptions()
      .then((options) => {
        setSetupOptions(options);
        setWorkspaceId((current) => current || options.defaults.workspace_id);
      })
      .catch(() => setLoadError(true));
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const frame = window.requestAnimationFrame(() =>
      firstChoiceRef.current?.focus(),
    );
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
      if (event.key !== "Tab") return;
      const focusable = Array.from(
        modalRef.current?.querySelectorAll<HTMLElement>(
          'button:not([disabled]), select:not([disabled]), input:not([disabled]), [tabindex]:not([tabindex="-1"])',
        ) ?? [],
      ).filter((element) => element.offsetParent !== null);
      const first = focusable[0];
      const last = focusable.at(-1);
      if (!first || !last) return;
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.cancelAnimationFrame(frame);
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [onClose, open]);

  const selectPreset = useCallback((preset: WorkspacePreset) => {
    setWorkspaceId(preset.id);
    setWorkspacePath(null);
    setStoredWorkspaceId(preset.id);
    setStoredWorkspacePath(null);
  }, []);

  const browseFolder = useCallback(async () => {
    const currentPreset = setupOptions?.workspaces.find(
      (workspace) => workspace.id === workspaceId,
    );
    const defaultPath =
      workspacePath ??
      currentPreset?.path ??
      setupOptions?.workspaces.find((workspace) => workspace.available)?.path ??
      null;
    const picked = await pickWorkspaceFolder(defaultPath);
    if (!picked) return;
    setWorkspaceId(CUSTOM_WORKSPACE_ID);
    setWorkspacePath(picked);
    setStoredWorkspaceId(CUSTOM_WORKSPACE_ID);
    setStoredWorkspacePath(picked);
  }, [setupOptions?.workspaces, workspaceId, workspacePath]);

  if (!open) return null;

  const workspaces = setupOptions?.workspaces ?? [];
  const isCustom = workspaceId === CUSTOM_WORKSPACE_ID;
  const selectedPreset = workspaces.find(
    (workspace) => workspace.id === workspaceId,
  );
  const canCreate = isCustom
    ? Boolean(workspacePath?.trim())
    : Boolean(selectedPreset?.available && selectedPreset.path);

  const submit = () => {
    if (!canCreate) return;
    const nextPath = isCustom ? workspacePath : null;
    setStoredWorkspaceId(workspaceId);
    setStoredWorkspacePath(nextPath);
    onCreate({
      workspaceId,
      workspacePath: nextPath,
      topic: initialTopic?.trim() || null,
    });
  };

  return (
    <div className="ns-overlay" role="presentation" onMouseDown={onClose}>
      <div
        ref={modalRef}
        className="ns-modal ns-modal--workspace"
        role="dialog"
        aria-modal="true"
        aria-labelledby="new-session-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <header className="ns-modal__head">
          <div>
            <h2 className="ns-modal__title" id="new-session-title">
              새 세션
            </h2>
            <p className="ns-modal__sub">작업할 워크스페이스를 선택하세요.</p>
          </div>
          <button
            type="button"
            className="icon-btn"
            onClick={onClose}
            aria-label="새 세션 닫기"
          >
            ×
          </button>
        </header>

        <div className="ns-modal__body scroll-y">
          <div className="ns-recent__list" role="list">
            {workspaces.map((workspace, index) => {
              const active = !isCustom && workspace.id === workspaceId;
              return (
                <button
                  key={workspace.id}
                  ref={index === 0 ? firstChoiceRef : undefined}
                  type="button"
                  className={`ns-recent__item${active ? " is-active" : ""}`}
                  disabled={!workspace.available}
                  onClick={() => selectPreset(workspace)}
                  aria-pressed={active}
                >
                  <span className="ns-recent__path">
                    {workspace.path ?? workspace.label}
                  </span>
                  <span className="ns-recent__time">{workspace.label}</span>
                  {active ? (
                    <span className="ns-recent__check" aria-hidden="true">
                      ✓
                    </span>
                  ) : null}
                </button>
              );
            })}
            <button
              ref={workspaces.length === 0 ? firstChoiceRef : undefined}
              type="button"
              className={`ns-recent__item${isCustom ? " is-active" : ""}`}
              onClick={() => void browseFolder()}
              aria-pressed={isCustom}
            >
              <span className="ns-recent__path">
                {isCustom && workspacePath ? workspacePath : "다른 폴더 선택…"}
              </span>
              {isCustom ? (
                <span className="ns-recent__check" aria-hidden="true">
                  ✓
                </span>
              ) : null}
            </button>
          </div>
          {loadError ? (
            <p className="ns-block__hint" role="alert">
              워크스페이스를 불러오지 못했습니다. API 연결을 확인하세요.
            </p>
          ) : null}
        </div>

        <footer className="ns-modal__foot">
          <span className="ns-modal__foot-hint">
            에이전트와 모델은 composer에서 /model로 변경할 수 있습니다.
          </span>
          <div className="ns-modal__foot-actions">
            <button type="button" className="btn" onClick={onClose}>
              취소
            </button>
            <button
              type="button"
              className="btn btn--primary"
              disabled={!canCreate}
              onClick={submit}
            >
              세션 만들기
            </button>
          </div>
        </footer>
      </div>
    </div>
  );
}
