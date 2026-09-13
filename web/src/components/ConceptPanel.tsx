import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  IdeationRequestError,
  fetchSessionIdeation,
  patchSessionIdeation,
  type IdeationCommandBody,
} from "../api/client";
import {
  actionRequestId,
  buildCandidateRows,
  buildCombineCommand,
  buildRejectCommand,
  buildResetCommand,
  buildSelectCommand,
  combinedSelectionRow,
  keyboardIntent,
  shouldReloadAfter,
  stageView,
  statusAfterReload,
  statusFromError,
  type ConceptPanelStatus,
  type IdeationState,
} from "../utils/conceptPanelView";

type Props = {
  sessionId: string | null;
  /** Bumped by the caller after a room turn so the panel refetches. */
  reloadKey?: number | string;
};

/** Candidate comparison + selection for the idea lane (RI-08).
 *
 * Renders nothing for a session without ideation state — every existing
 * session keeps the surface it had. Choosing here records a decision; it never
 * approves execution.
 */
export function ConceptPanel({ sessionId, reloadKey }: Props) {
  const [state, setState] = useState<IdeationState | null>(null);
  const [status, setStatus] = useState<ConceptPanelStatus>({ kind: "idle" });
  const [focusIndex, setFocusIndex] = useState(0);
  const [compareIds, setCompareIds] = useState<string[]>([]);
  const [pending, setPending] = useState(false);
  const listRef = useRef<HTMLDivElement | null>(null);

  const load = useCallback(
    async (keepStatus?: ConceptPanelStatus) => {
      if (!sessionId) {
        setState(null);
        setStatus({ kind: "idle" });
        return;
      }
      setStatus({ kind: "loading" });
      try {
        const res = await fetchSessionIdeation(sessionId);
        setState(res.ideation);
        setStatus(statusAfterReload(keepStatus));
      } catch (err) {
        setState(null);
        setStatus(statusFromError(err as IdeationRequestError));
      }
    },
    [sessionId],
  );

  useEffect(() => {
    void load();
  }, [load, reloadKey]);

  const rows = useMemo(() => buildCandidateRows(state), [state]);
  const combined = useMemo(() => combinedSelectionRow(state), [state]);
  const stage = useMemo(() => stageView(state), [state]);

  const send = useCallback(
    async (body: IdeationCommandBody) => {
      if (!sessionId || pending) return;
      setPending(true);
      try {
        const res = await patchSessionIdeation(sessionId, body);
        setState(res.ideation);
        setStatus({ kind: "idle" });
        setCompareIds([]);
      } catch (err) {
        const next = statusFromError(err as IdeationRequestError);
        setStatus(next);
        // A stale write is resolved by reading the newer state, never by
        // retrying the same write over it.
        if (shouldReloadAfter(next)) await load(next);
      } finally {
        setPending(false);
      }
    },
    [sessionId, pending, load],
  );

  const revision = state?.revision ?? 0;
  const rid = (action: string) =>
    actionRequestId(sessionId ?? "", revision, action);

  const onSelect = (optionId: string) =>
    void send(
      buildSelectCommand({
        optionId,
        revision,
        requestId: rid(`select:${optionId}`),
      }),
    );

  const onReject = (optionId: string) =>
    void send(
      buildRejectCommand({
        optionId,
        revision,
        requestId: rid(`reject:${optionId}`),
      }),
    );

  const onCombine = () =>
    void send(
      buildCombineCommand({
        parentIds: compareIds,
        revision,
        requestId: rid(`combine:${compareIds.join("+")}`),
      }),
    );

  const onReset = () =>
    void send(buildResetCommand({ revision, requestId: rid("reset") }));

  const toggleCompare = (optionId: string) =>
    setCompareIds((prev) =>
      prev.includes(optionId)
        ? prev.filter((id) => id !== optionId)
        : [...prev, optionId],
    );

  const onKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    const intent = keyboardIntent({
      key: event.key,
      index: focusIndex,
      count: rows.length,
    });
    if (intent.kind === "none") return;
    event.preventDefault();
    if (intent.kind === "move") {
      setFocusIndex(intent.index);
      const next = listRef.current?.querySelectorAll<HTMLElement>(
        "[data-concept-candidate]",
      )?.[intent.index];
      next?.focus();
      return;
    }
    const row = rows[focusIndex];
    if (!row) return;
    if (intent.kind === "select") onSelect(row.id);
    else if (intent.kind === "reject") onReject(row.id);
    else if (intent.kind === "toggleCompare") toggleCompare(row.id);
  };

  if (!sessionId || status.kind === "absent") return null;
  if (status.kind === "loading" && !state) {
    return (
      <aside className="concept-panel" aria-label="구상">
        <p className="concept-panel__muted">구상을 불러오는 중…</p>
      </aside>
    );
  }
  if (!state) {
    return status.kind === "error" ? (
      <aside className="concept-panel" aria-label="구상">
        <p className="concept-panel__error" role="alert">
          {status.message}
        </p>
        <button type="button" onClick={() => void load()}>
          다시 시도
        </button>
      </aside>
    ) : null;
  }

  return (
    <aside className="concept-panel" aria-label="구상">
      <header className="concept-panel__head">
        <span className="concept-panel__stage">{stage?.label}</span>
        <span className="concept-panel__rev">rev {revision}</span>
      </header>
      {stage ? <p className="concept-panel__hint">{stage.hint}</p> : null}

      {status.kind === "stale" || status.kind === "busy" ? (
        <p className="concept-panel__notice" role="status">
          {status.message}
        </p>
      ) : null}
      {status.kind === "error" ? (
        <p className="concept-panel__error" role="alert">
          {status.message}
        </p>
      ) : null}

      {combined ? (
        <p className="concept-panel__combined">
          합친 구상 <strong>{combined.title}</strong> ←{" "}
          {combined.parents.join(" + ")}
        </p>
      ) : null}

      <div
        className="concept-panel__list"
        role="listbox"
        aria-label="구상 후보"
        ref={listRef}
        onKeyDown={onKeyDown}
      >
        {rows.map((row, index) => (
          <div
            key={row.id}
            data-concept-candidate
            role="option"
            aria-selected={row.selected}
            tabIndex={index === focusIndex ? 0 : -1}
            className={[
              "concept-candidate",
              row.selected ? "is-selected" : "",
              row.rejected ? "is-rejected" : "",
              compareIds.includes(row.id) ? "is-comparing" : "",
            ]
              .filter(Boolean)
              .join(" ")}
            onFocus={() => setFocusIndex(index)}
          >
            <h4 className="concept-candidate__title">{row.title}</h4>
            {row.agent ? (
              <span className="concept-candidate__agent">{row.agent}</span>
            ) : null}
            {row.unparsedText ? (
              <pre className="concept-candidate__raw">{row.unparsedText}</pre>
            ) : (
              <dl className="concept-candidate__fields">
                {row.fields.map((field) => (
                  <div key={field.label}>
                    <dt>{field.label}</dt>
                    <dd>{field.value}</dd>
                  </div>
                ))}
              </dl>
            )}
            <div className="concept-candidate__actions">
              <button
                type="button"
                disabled={pending}
                onClick={() => onSelect(row.id)}
              >
                {row.selected ? "선택됨" : "이걸로"}
              </button>
              <button
                type="button"
                disabled={pending}
                onClick={() => toggleCompare(row.id)}
              >
                {compareIds.includes(row.id) ? "합치기 해제" : "합치기"}
              </button>
              <button
                type="button"
                disabled={pending}
                onClick={() => onReject(row.id)}
              >
                {row.rejected ? "기각됨" : "아님"}
              </button>
            </div>
          </div>
        ))}
      </div>

      <footer className="concept-panel__foot">
        <button
          type="button"
          disabled={pending || compareIds.length < 2}
          onClick={onCombine}
        >
          고른 {compareIds.length}개 합치기
        </button>
        <button type="button" disabled={pending} onClick={onReset}>
          모두 아님 · 다시 탐색
        </button>
        <p className="concept-panel__muted">
          방향 수정은 대화로도 됩니다. 선택은 실행 승인이 아닙니다.
        </p>
      </footer>
    </aside>
  );
}
