type Props = {
  query: string;
  paths: string[];
  loading?: boolean;
  onPick: (path: string) => void;
};

export function ComposerMentionMenu({ query, paths, loading, onPick }: Props) {
  const q = query.toLowerCase();
  const filtered = paths
    .filter((p) => !q || p.toLowerCase().includes(q))
    .slice(0, 8);

  if (!loading && filtered.length === 0) return null;

  return (
    <div
      className="composer-mention-menu"
      role="listbox"
      aria-label="File mentions"
    >
      {loading ? (
        <div className="composer-mention-menu__hint">Loading files…</div>
      ) : (
        filtered.map((path) => (
          <button
            key={path}
            type="button"
            role="option"
            className="composer-mention-menu__item"
            onMouseDown={(e) => {
              e.preventDefault();
              onPick(path);
            }}
          >
            @{path}
          </button>
        ))
      )}
    </div>
  );
}
