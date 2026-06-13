import { useCallback, useEffect, useState } from "react";
import {
  listWorkspaceFileRoots,
  listWorkspaceFiles,
  readWorkspaceFile,
  writeSessionFile,
  type WorkspaceFileContent,
  type WorkspaceFileEntry,
  type WorkspaceFileRoot,
} from "../api/client";
import { FilePreview } from "./FilePreview";

type Props = {
  sessionId: string;
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
    <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth={1.7} strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z" />
    </svg>
  );
}

function FileGlyph() {
  return (
    <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" strokeWidth={1.6} strokeLinecap="round" strokeLinejoin="round" aria-hidden>
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
          <span className={`files-row__twisty${open ? " is-open" : ""}`} aria-hidden>
            ▸
          </span>
          <FolderIcon />
          <span className="files-row__name">{dirPath.split("/").pop()}</span>
        </button>
      ) : null}
      {open ? (
        <div className="files-children">
          {loading ? (
            <div className="files-hint" style={{ paddingLeft: 8 + indent + 13 }}>
              loading…
            </div>
          ) : null}
          {error ? (
            <div className="files-error" style={{ paddingLeft: 8 + indent + 13 }}>
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
              </button>
            );
          })}
          {entries && entries.length === 0 ? (
            <div className="files-hint" style={{ paddingLeft: 8 + indent + 13 }}>
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
        <svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z" />
          <path d="M14 2v6h6" />
        </svg>
      </span>
      <span className="empty-state__title">{title}</span>
      <span className="empty-state__hint">{hint}</span>
    </div>
  );
}

export function WorkspaceFilesPanel({ sessionId }: Props) {
  const [roots, setRoots] = useState<WorkspaceFileRoot[] | null>(null);
  const [activeRoot, setActiveRoot] = useState<string | null>(null);
  const [rootsError, setRootsError] = useState<string | null>(null);

  const [selected, setSelected] = useState<string | null>(null);
  const [content, setContent] = useState<WorkspaceFileContent | null>(null);
  const [draft, setDraft] = useState("");
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [viewerError, setViewerError] = useState<string | null>(null);

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
        if (!cancelled) setRootsError(e instanceof Error ? e.message : "load failed");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [sessionId]);

  const openFile = useCallback(
    async (path: string) => {
      if (!activeRoot) return;
      setSelected(path);
      setContent(null);
      setViewerError(null);
      setDirty(false);
      try {
        const res = await readWorkspaceFile(sessionId, activeRoot, path);
        setContent(res);
        setDraft(res.content ?? "");
      } catch (e) {
        setViewerError(e instanceof Error ? e.message : "read failed");
      }
    },
    [sessionId, activeRoot],
  );

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
  const fileName = selected?.split("/").pop() ?? selected;

  return (
    <div className="files-tab">
      <aside className="files-tab__sidebar">
        <div className="files-tab__head">
          <FolderIcon />
          Files
        </div>
        {roots && roots.length > 1 ? (
          <div className="files-roots">
            {roots.map((r) => (
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
                {r.is_primary ? <span className="files-root__tag">primary</span> : null}
              </button>
            ))}
          </div>
        ) : null}
        <div className="files-tree">
          {rootsError ? <div className="files-error">{rootsError}</div> : null}
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
      </aside>

      <section className="files-viewer">
        {selected == null ? (
          <ViewerEmpty
            title="Select a file"
            hint="Browse the workspace tree on the left. Files under the session attachments/ are editable; repo files are read-only and edited through Execute."
          />
        ) : (
          <>
            <header className="files-viewer__head">
              <span className="files-viewer__path" title={selected}>
                {fileName}
              </span>
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
                <span className="files-viewer__readonly">read-only · edit via Execute</span>
              )}
            </header>
            <div className="files-viewer__body">
              {viewerError ? <div className="files-error">{viewerError}</div> : null}
              {content == null && !viewerError ? (
                <div className="files-hint">loading…</div>
              ) : null}
              {content && activeRoot ? (
                writable && content.kind === "text" ? (
                  <textarea
                    className="files-editor"
                    value={draft}
                    spellCheck={false}
                    onChange={(e) => {
                      setDraft(e.target.value);
                      setDirty(true);
                    }}
                  />
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
                <div className="files-hint files-hint--foot">truncated for preview</div>
              ) : null}
            </div>
          </>
        )}
      </section>
    </div>
  );
}
