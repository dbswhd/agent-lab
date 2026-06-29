import {
  useCallback,
  useEffect,
  useRef,
  useState,
  lazy,
  Suspense,
} from "react";
import type { CSSProperties } from "react";
import {
  listWorkspaceFileRoots,
  listWorkspaceFiles,
  readWorkspaceFile,
  writeSessionFile,
  type WorkspaceFileContent,
  type WorkspaceFileEntry,
  type WorkspaceFileRoot,
} from "../api/client";
import { collectMentionPaths } from "../hooks/useComposerMentionPaths";
import {
  FILES_SIDEBAR_MIN_WIDTH,
  clampFilesSidebarWidth,
  getFilesSidebarWidth,
  setFilesSidebarWidth,
} from "../utils/inspectorPanePrefs";
import {
  getVisibleRootIds,
  resolveVisibleRoots,
  setVisibleRootIds,
  toggleVisibleRoot,
} from "../utils/filesRootPrefs";
import { FilePreview } from "./FilePreview";

const FilesMonacoEditor = lazy(() =>
  import("./FilesMonacoEditor").then((m) => ({ default: m.FilesMonacoEditor })),
);

type Props = {
  sessionId: string;
  /** Open this path under session root once roots are loaded. */
  focusPath?: string | null;
  focusRootId?: string;
  /** Bump to re-open the same path (e.g. plan.md updated). */
  focusRevision?: number;
};

function joinPath(dir: string, name: string): string {
  return dir ? `${dir}/${name}` : name;
}

/** A writable target is only the session root's attachments/ subtree. */
function isWritable(rootId: string, path: string): boolean {
  return rootId === "session" && path.startsWith("attachments/");
}

function FolderIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      width="14"
      height="14"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.7}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z" />
    </svg>
  );
}

function FileGlyph() {
  return (
    <svg
      viewBox="0 0 24 24"
      width="13"
      height="13"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.6}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z" />
      <path d="M14 2v6h6" />
    </svg>
  );
}

/** One directory level — fetches its children lazily on expand. */
function DirNode({
  sessionId,
  rootId,
  dirPath,
  depth,
  selectedPath,
  onSelectFile,
}: {
  sessionId: string;
  rootId: string;
  dirPath: string;
  depth: number;
  selectedPath: string | null;
  onSelectFile: (path: string) => void;
}) {
  const [open, setOpen] = useState(depth === 0);
  const [entries, setEntries] = useState<WorkspaceFileEntry[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await listWorkspaceFiles(sessionId, rootId, dirPath);
      setEntries(res.entries);
    } catch (e) {
      setError(e instanceof Error ? e.message : "load failed");
    } finally {
      setLoading(false);
    }
  }, [sessionId, rootId, dirPath]);

  useEffect(() => {
    if (open && entries === null && !loading) void load();
  }, [open, entries, loading, load]);

  const indent = depth * 13;

  return (
    <div className="files-node">
      {depth > 0 ? (
        <button
          type="button"
          className="files-row files-row--dir"
          style={{ paddingLeft: 8 + indent }}
          aria-expanded={open}
          onClick={() => setOpen((v) => !v)}
        >
          <span
            className={`files-row__twisty${open ? " is-open" : ""}`}
            aria-hidden
          >
            ▸
          </span>
          <FolderIcon />
          <span className="files-row__name">{dirPath.split("/").pop()}</span>
        </button>
      ) : null}
      {open ? (
        <div className="files-children">
          {loading ? (
            <div
              className="files-hint"
              style={{ paddingLeft: 8 + indent + 13 }}
            >
              loading…
            </div>
          ) : null}
          {error ? (
            <div
              className="files-error"
              style={{ paddingLeft: 8 + indent + 13 }}
            >
              {error}
            </div>
          ) : null}
          {entries?.map((entry) => {
            const childPath = joinPath(dirPath, entry.name);
            if (entry.type === "dir") {
              return (
                <DirNode
                  key={childPath}
                  sessionId={sessionId}
                  rootId={rootId}
                  dirPath={childPath}
                  depth={depth + 1}
                  selectedPath={selectedPath}
                  onSelectFile={onSelectFile}
                />
              );
            }
            return (
              <button
                type="button"
                key={childPath}
                className={`files-row files-row--file${
                  selectedPath === childPath ? " is-selected" : ""
                }`}
                style={{ paddingLeft: 8 + (depth + 1) * 13 }}
                onClick={() => onSelectFile(childPath)}
              >
                <FileGlyph />
                <span className="files-row__name">{entry.name}</span>
                {entry.git_status ? (
                  <span
                    className="files-row__git"
                    data-status={entry.git_status}
                    title={`git ${entry.git_status}`}
                  >
                    {entry.git_status}
                  </span>
                ) : null}
              </button>
            );
          })}
          {entries && entries.length === 0 ? (
            <div
              className="files-hint"
              style={{ paddingLeft: 8 + indent + 13 }}
            >
              empty
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function ViewerEmpty({ title, hint }: { title: string; hint: string }) {
  return (
    <div className="empty-state">
      <span className="empty-state__icon" aria-hidden>
        <svg
          viewBox="0 0 24 24"
          width="24"
          height="24"
          fill="none"
          stroke="currentColor"
          strokeWidth={1.5}
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z" />
          <path d="M14 2v6h6" />
        </svg>
      </span>
      <span className="empty-state__title">{title}</span>
      <span className="empty-state__hint">{hint}</span>
    </div>
  );
}

function TreeToggleIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      width="16"
      height="16"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.7}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <rect x="3" y="3" width="7" height="18" rx="1" />
      <path d="M14 8h7M14 12h7M14 16h4" />
    </svg>
  );
}

function EditFoldersIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      width="14"
      height="14"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.7}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="M12 20h9" />
      <path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z" />
    </svg>
  );
}

function FilesRootsEditor({
  roots,
  visibleIds,
  onChange,
  onClose,
}: {
  roots: WorkspaceFileRoot[];
  visibleIds: string[];
  onChange: (ids: string[]) => void;
  onClose: () => void;
}) {
  const allIds = roots.map((root) => root.root_id);
  const shown = visibleIds.length ? visibleIds : allIds;

  return (
    <div className="files-roots-edit">
      <div className="files-roots-edit__head">
        <span>Workspaces shown</span>
        <button
          type="button"
          className="files-roots-edit__done"
          onClick={onClose}
        >
          Done
        </button>
      </div>
      <ul className="files-roots-edit__list">
        {roots.map((root) => (
          <li key={root.root_id}>
            <label className="files-roots-edit__item">
              <input
                type="checkbox"
                checked={shown.includes(root.root_id)}
                disabled={root.missing}
                onChange={() =>
                  onChange(toggleVisibleRoot(visibleIds, allIds, root.root_id))
                }
              />
              <span className="files-roots-edit__label">{root.label}</span>
              {root.is_primary ? (
                <span className="files-root__tag">primary</span>
              ) : null}
            </label>
          </li>
        ))}
      </ul>
      <button
        type="button"
        className="files-roots-edit__reset"
        onClick={() => onChange([])}
      >
        Show all
      </button>
    </div>
  );
}

function FilePathBreadcrumb({
  rootLabel,
  path,
}: {
  rootLabel: string;
  path: string;
}) {
  const segments = path.split("/").filter(Boolean);
  return (
    <nav
      className="files-viewer__breadcrumb"
      aria-label="File path"
      title={`${rootLabel}/${path}`}
    >
      <span className="files-viewer__crumb files-viewer__crumb--root">
        {rootLabel}
      </span>
      {segments.map((segment, index) => (
        <span
          key={`${index}-${segment}`}
          className={`files-viewer__crumb${
            index === segments.length - 1 ? " files-viewer__crumb--leaf" : ""
          }`}
        >
          <span className="files-viewer__sep" aria-hidden>
            ›
          </span>
          {segment}
        </span>
      ))}
    </nav>
  );
}

export function WorkspaceFilesPanel({
  sessionId,
  focusPath = null,
  focusRootId = "session",
  focusRevision = 0,
}: Props) {
  const [roots, setRoots] = useState<WorkspaceFileRoot[] | null>(null);
  const [activeRoot, setActiveRoot] = useState<string | null>(null);
  const [rootsError, setRootsError] = useState<string | null>(null);

  const [selected, setSelected] = useState<string | null>(null);
  const [content, setContent] = useState<WorkspaceFileContent | null>(null);
  const [draft, setDraft] = useState("");
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [viewerError, setViewerError] = useState<string | null>(null);
  const [pathSuggestions, setPathSuggestions] = useState<string[]>([]);
  const [sidebarWidth, setSidebarWidth] = useState(getFilesSidebarWidth);
  const [treeVisible, setTreeVisible] = useState(true);
  const [isResizing, setIsResizing] = useState(false);
  const [visibleRootIds, setVisibleRootIdsState] = useState<string[]>([]);
  const [rootsEditing, setRootsEditing] = useState(false);
  const dragRef = useRef({
    startX: 0,
    startWidth: FILES_SIDEBAR_MIN_WIDTH,
  });

  useEffect(() => {
    let cancelled = false;
    void collectMentionPaths(sessionId).then((paths) => {
      if (!cancelled) setPathSuggestions(paths);
    });
    return () => {
      cancelled = true;
    };
  }, [sessionId]);

  // Load roots when the session changes; pick the primary (binding) root.
  useEffect(() => {
    let cancelled = false;
    setRoots(null);
    setRootsError(null);
    setSelected(null);
    setContent(null);
    void (async () => {
      try {
        const res = await listWorkspaceFileRoots(sessionId);
        if (cancelled) return;
        setRoots(res.roots);
        const primary =
          res.roots.find((r) => r.is_primary && !r.missing) ??
          res.roots.find((r) => !r.missing) ??
          res.roots[0];
        setActiveRoot(primary?.root_id ?? null);
      } catch (e) {
        if (!cancelled)
          setRootsError(e instanceof Error ? e.message : "load failed");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [sessionId]);

  useEffect(() => {
    setVisibleRootIdsState(getVisibleRootIds(sessionId));
    setRootsEditing(false);
  }, [sessionId]);

  const displayRoots =
    roots == null ? null : resolveVisibleRoots(roots, visibleRootIds);

  useEffect(() => {
    if (!displayRoots?.length) return;
    if (
      activeRoot &&
      displayRoots.some((root) => root.root_id === activeRoot)
    ) {
      return;
    }
    const next =
      displayRoots.find((root) => root.is_primary && !root.missing) ??
      displayRoots.find((root) => !root.missing) ??
      displayRoots[0];
    setActiveRoot(next?.root_id ?? null);
  }, [displayRoots, activeRoot]);

  const handleVisibleRootsChange = useCallback(
    (rootIds: string[]) => {
      setVisibleRootIdsState(rootIds);
      setVisibleRootIds(sessionId, rootIds);
    },
    [sessionId],
  );

  useEffect(() => {
    if (selected) setTreeVisible(false);
    else setTreeVisible(true);
  }, [selected]);

  const onResizePointerDown = useCallback(
    (event: React.PointerEvent<HTMLDivElement>) => {
      event.preventDefault();
      dragRef.current = { startX: event.clientX, startWidth: sidebarWidth };
      setIsResizing(true);
      event.currentTarget.setPointerCapture(event.pointerId);
    },
    [sidebarWidth],
  );

  const onResizePointerMove = useCallback(
    (event: React.PointerEvent<HTMLDivElement>) => {
      if (!isResizing) return;
      const delta = event.clientX - dragRef.current.startX;
      setSidebarWidth(
        clampFilesSidebarWidth(dragRef.current.startWidth + delta),
      );
    },
    [isResizing],
  );

  const finishResize = useCallback(
    (event: React.PointerEvent<HTMLDivElement>, finalWidth: number) => {
      if (!isResizing) return;
      setIsResizing(false);
      if (event.currentTarget.hasPointerCapture(event.pointerId)) {
        event.currentTarget.releasePointerCapture(event.pointerId);
      }
      const clamped = clampFilesSidebarWidth(finalWidth);
      setSidebarWidth(clamped);
      setFilesSidebarWidth(clamped);
    },
    [isResizing],
  );

  const openFile = useCallback(
    async (path: string, rootId?: string) => {
      const root = rootId ?? activeRoot;
      if (!root) return;
      if (rootId && rootId !== activeRoot) {
        setActiveRoot(rootId);
      }
      setSelected(path);
      setContent(null);
      setViewerError(null);
      setDirty(false);
      try {
        const res = await readWorkspaceFile(sessionId, root, path);
        setContent(res);
        setDraft(res.content ?? "");
      } catch (e) {
        setViewerError(e instanceof Error ? e.message : "read failed");
      }
    },
    [sessionId, activeRoot],
  );

  useEffect(() => {
    if (!focusPath || !roots?.length) return;
    const root =
      roots.find((r) => r.root_id === focusRootId && !r.missing) ??
      roots.find((r) => r.root_id === "session" && !r.missing) ??
      roots.find((r) => !r.missing);
    if (!root) return;
    void openFile(focusPath, root.root_id);
  }, [focusPath, focusRootId, focusRevision, roots, openFile]);

  const save = useCallback(async () => {
    if (!activeRoot || !selected) return;
    setSaving(true);
    setViewerError(null);
    try {
      await writeSessionFile(sessionId, activeRoot, selected, draft);
      setDirty(false);
      const res = await readWorkspaceFile(sessionId, activeRoot, selected);
      setContent(res);
      setDraft(res.content ?? "");
    } catch (e) {
      setViewerError(e instanceof Error ? e.message : "save failed");
    } finally {
      setSaving(false);
    }
  }, [sessionId, activeRoot, selected, draft]);

  const writable =
    activeRoot != null && selected != null && isWritable(activeRoot, selected);
  const activeRootLabel =
    roots?.find((r) => r.root_id === activeRoot)?.label ?? activeRoot ?? "";

  const tabStyle: CSSProperties & Record<"--files-sidebar-width", string> = {
    "--files-sidebar-width": `${sidebarWidth}px`,
  };

  return (
    <div
      className={[
        "files-tab",
        selected ? "files-tab--file-open" : "",
        treeVisible ? "files-tab--tree-visible" : "files-tab--tree-hidden",
        isResizing ? "files-tab--resizing" : "",
      ]
        .filter(Boolean)
        .join(" ")}
      style={tabStyle}
    >
      {treeVisible ? (
        <aside className="files-tab__sidebar">
          <div className="files-tab__head">
            <span className="files-tab__head-label">
              <FolderIcon />
              Files
            </span>
            {roots && roots.length > 0 ? (
              <button
                type="button"
                className={`files-tab__edit${rootsEditing ? " is-active" : ""}`}
                aria-label="Edit workspace roots"
                aria-pressed={rootsEditing}
                title="Edit workspaces shown"
                onClick={() => setRootsEditing((v) => !v)}
              >
                <EditFoldersIcon />
              </button>
            ) : null}
          </div>
          {rootsEditing && roots ? (
            <FilesRootsEditor
              roots={roots}
              visibleIds={visibleRootIds}
              onChange={handleVisibleRootsChange}
              onClose={() => setRootsEditing(false)}
            />
          ) : null}
          {displayRoots && displayRoots.length > 0 && !rootsEditing ? (
            <div className="files-roots">
              {displayRoots.map((r) => (
                <button
                  type="button"
                  key={r.root_id}
                  disabled={r.missing}
                  title={r.missing ? "path missing on disk" : r.label}
                  className={`files-root${activeRoot === r.root_id ? " is-active" : ""}${
                    r.missing ? " is-missing" : ""
                  }`}
                  onClick={() => {
                    setActiveRoot(r.root_id);
                    setSelected(null);
                    setContent(null);
                  }}
                >
                  <span className="files-root__label">{r.label}</span>
                  {r.is_primary ? (
                    <span className="files-root__tag">primary</span>
                  ) : null}
                </button>
              ))}
            </div>
          ) : null}
          <div className="files-tree">
            {rootsError ? (
              <div className="files-error">{rootsError}</div>
            ) : null}
            {roots === null ? (
              <div className="files-hint">loading roots…</div>
            ) : activeRoot ? (
              <DirNode
                key={activeRoot}
                sessionId={sessionId}
                rootId={activeRoot}
                dirPath=""
                depth={0}
                selectedPath={selected}
                onSelectFile={openFile}
              />
            ) : (
              <div className="files-hint">no readable roots</div>
            )}
          </div>
          <div
            className="files-tab__resize-handle"
            role="separator"
            aria-orientation="vertical"
            aria-label="Files explorer width"
            onPointerDown={onResizePointerDown}
            onPointerMove={onResizePointerMove}
            onPointerUp={(event) => finishResize(event, sidebarWidth)}
            onPointerCancel={(event) => finishResize(event, sidebarWidth)}
          />
        </aside>
      ) : null}

      <section className="files-viewer">
        {selected == null ? (
          <ViewerEmpty
            title="Select a file"
            hint="Browse the workspace tree on the left. Files under the session attachments/ are editable; repo files are read-only and edited through Execute."
          />
        ) : (
          <>
            <header className="files-viewer__head">
              <div className="files-viewer__head-start">
                <button
                  type="button"
                  className="files-viewer__tree-toggle"
                  aria-label={treeVisible ? "Hide explorer" : "Show explorer"}
                  aria-pressed={treeVisible}
                  title={treeVisible ? "Hide explorer" : "Show explorer"}
                  onClick={() => setTreeVisible((v) => !v)}
                >
                  <TreeToggleIcon />
                </button>
                <FilePathBreadcrumb
                  rootLabel={activeRootLabel}
                  path={selected}
                />
              </div>
              {writable ? (
                <button
                  type="button"
                  className="files-viewer__save"
                  disabled={!dirty || saving}
                  onClick={() => void save()}
                >
                  {saving ? "Saving…" : "Save"}
                </button>
              ) : (
                <span className="files-viewer__readonly">
                  read-only · edit via Execute
                </span>
              )}
            </header>
            <div className="files-viewer__body">
              {viewerError ? (
                <div className="files-error">{viewerError}</div>
              ) : null}
              {content == null && !viewerError ? (
                <div className="files-hint">loading…</div>
              ) : null}
              {content && activeRoot ? (
                writable && content.kind === "text" ? (
                  <Suspense
                    fallback={<div className="files-hint">loading editor…</div>}
                  >
                    <FilesMonacoEditor
                      path={selected}
                      value={draft}
                      pathSuggestions={pathSuggestions}
                      onChange={(next) => {
                        setDraft(next);
                        setDirty(true);
                      }}
                    />
                  </Suspense>
                ) : (
                  <FilePreview
                    sessionId={sessionId}
                    rootId={activeRoot}
                    path={selected}
                    content={content}
                  />
                )
              ) : null}
              {content?.truncated ? (
                <div className="files-hint files-hint--foot">
                  truncated for preview
                </div>
              ) : null}
            </div>
          </>
        )}
      </section>
    </div>
  );
}
