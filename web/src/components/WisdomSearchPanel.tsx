import { useCallback, useState } from "react";
import {
  fetchSessionWisdomSearch,
  rebuildSessionWisdomIndex,
  type WisdomHit,
  type WisdomIndexStatus,
} from "../api/client";

type Props = {
  sessionId: string;
  index?: WisdomIndexStatus | null;
  ko?: boolean;
};

export function WisdomSearchPanel({ sessionId, index, ko = true }: Props) {
  const enabled = Boolean(index?.enabled);
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<WisdomHit[]>([]);
  const [busy, setBusy] = useState(false);
  const [rebuildBusy, setRebuildBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const runSearch = useCallback(async () => {
    const q = query.trim();
    if (!q || !enabled) return;
    setBusy(true);
    setError(null);
    try {
      const res = await fetchSessionWisdomSearch(
        sessionId,
        q,
        12,
        Boolean(index?.cross_session),
      );
      setHits([...(res.hits ?? []), ...(res.cross_session_hits ?? [])]);
    } catch (e) {
      setHits([]);
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, [enabled, query, sessionId]);

  const handleRebuild = useCallback(async () => {
    if (!enabled) return;
    setRebuildBusy(true);
    setError(null);
    try {
      await rebuildSessionWisdomIndex(sessionId);
      if (query.trim()) {
        const res = await fetchSessionWisdomSearch(sessionId, query.trim(), 12);
        setHits(res.hits ?? []);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setRebuildBusy(false);
    }
  }, [enabled, query, sessionId]);

  if (!enabled) return null;

  return (
    <section className="wisdom-search" data-testid="wisdom-search-panel">
      <div className="wisdom-search__head">
        <span className="wisdom-search__title">
          {ko ? "미션 지식 검색" : "Mission wisdom search"}
        </span>
        <span className="wisdom-search__meta">
          {index?.document_count ?? 0} docs
          {index?.cross_session ? " · cross-session" : ""}
        </span>
      </div>
      <div className="wisdom-search__row">
        <input
          className="wisdom-search__input"
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") void runSearch();
          }}
          placeholder={ko ? "evidence · notepad 검색" : "Search evidence & notepads"}
          aria-label={ko ? "미션 지식 검색" : "Mission wisdom search"}
        />
        <button
          type="button"
          className="wisdom-search__btn"
          disabled={busy || !query.trim()}
          onClick={() => void runSearch()}
        >
          {busy ? "…" : ko ? "검색" : "Search"}
        </button>
        <button
          type="button"
          className="wisdom-search__btn wisdom-search__btn--ghost"
          disabled={rebuildBusy}
          onClick={() => void handleRebuild()}
        >
          {rebuildBusy ? "…" : ko ? "재색인" : "Rebuild"}
        </button>
      </div>
      {error ? <p className="wisdom-search__error">{error}</p> : null}
      {hits.length ? (
        <ul className="wisdom-search__hits">
          {hits.map((hit) => (
            <li
              key={`${hit.session_id ?? sessionId}:${hit.id ?? hit.title}`}
              className="wisdom-search__hit"
            >
              <span className="wisdom-search__hit-source">{hit.source}</span>
              <strong className="wisdom-search__hit-title">{hit.title}</strong>
              <p className="wisdom-search__hit-snippet">{hit.snippet}</p>
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}
