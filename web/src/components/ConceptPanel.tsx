import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  IdeationRequestError,
  fetchSessionIdeation,
  fetchSessionIdeationExport,
  patchSessionIdeation,
  runSynthesizeOnly,
  type IdeationCommandBody,
} from "../api/client";
import {
  actionRequestId,
  buildCandidateRows,
  buildCombineCommand,
  buildRejectCommand,
  buildResetCommand,
  buildSelectCommand,
  canRequestPlan,
  combinedSelectionRow,
  exportView,
  keyboardIntent,
  shouldReloadAfter,
  stageView,
  statusAfterReload,
  statusFromError,
  type ConceptPanelStatus,
  type IdeationExportView,
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
  const [exported, setExported] = useState<IdeationExportView | null>(null);
  const [exportNote, setExportNote] = useState("");
  const [constraintsText, setConstraintsText] = useState("");
  const [conceptText, setConceptText] = useState("");
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
        const constraints = res.ideation.brief?.constraints;
        setConstraintsText(
          Array.isArray(constraints) ? constraints.join("\n") : "",
        );
        setConceptText(String(res.ideation.concept?.summary ?? ""));
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

  const onSaveConditions = () =>
    void send({
      command: "condition",
      constraints: constraintsText
        .split("\n")
        .map((item) => item.trim())
        .filter(Boolean),
      expected_revision: revision,
      request_id: rid("condition"),
    });

  const onSaveConcept = () =>
    void send({
      command: "concept",
      concept: { summary: conceptText.trim() },
      expected_revision: revision,
      request_id: rid("concept"),
    });

  const onMakePlan = async () => {
    if (!sessionId || pending) return;
    setPending(true);
    try {
      const next = await patchSessionIdeation(sessionId, {
        command: "plan",
        expected_revision: revision,
        request_id: rid("plan"),
      });
      setState(next.ideation);
      setStatus({ kind: "loading" });
      await runSynthesizeOnly(sessionId, () => undefined, {
        requestId: `${sessionId}:${next.revision}:synthesize`,
      });
      await load();
      setStatus({ kind: "idle" });
    } catch (err) {
      setStatus(statusFromError(err as IdeationRequestError));
      await load();
    } finally {
      setPending(false);
    }
  };

  const runExport = useCallback(async () => {
    if (!sessionId) return null;
    const res = await fetchSessionIdeationExport(sessionId);
    const view = exportView(res);
    setExported(view);
    return view;
  }, [sessionId]);

  const onCopy = async () => {
    setExportNote("");
    try {
      const view = await runExport();
      if (!view) return;
      await navigator.clipboard.writeText(view.markdown);
      setExportNote(`복사했습니다 (rev ${view.revision})`);
    } catch {
      // Clipboard access fails on an insecure origin or without permission;
      // the document is still on screen to select by hand.
      setExportNote("클립보드를 쓸 수 없습니다. 아래 문서를 직접 복사하세요.");
    }
  };

  const onDownload = async () => {
    setExportNote("");
    try {
      const view = await runExport();
      if (!view) return;
      const url = URL.createObjectURL(
        new Blob([view.markdown], { type: "text/markdown;charset=utf-8" }),
      );
      const link = document.createElement("a");
      link.href = url;
      link.download = view.filename;
      link.click();
      URL.revokeObjectURL(url);
      setExportNote(`${view.filename} 내려받음`);
    } catch (err) {
      setExportNote(String((err as Error)?.message ?? "내보내기 실패"));
    }
  };

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
            {row.qualityMessage ? (
              <p className="concept-candidate__quality" role="status">
                {row.qualityMessage}
              </p>
            ) : null}
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
        {state.stage !== "explore" ? (
          <section className="concept-panel__editor" aria-label="구상 구체화">
            <label>
              현재 조건
              <textarea
                value={constraintsText}
                onChange={(event) => setConstraintsText(event.target.value)}
                rows={3}
              />
            </label>
            <button type="button" disabled={pending} onClick={onSaveConditions}>
              조건 저장
            </button>
            <label>
              구체화된 구상
              <textarea
                value={conceptText}
                onChange={(event) => setConceptText(event.target.value)}
                rows={4}
              />
            </label>
            <button type="button" disabled={pending} onClick={onSaveConcept}>
              구체화 저장
            </button>
            <button
              type="button"
              disabled={pending || !canRequestPlan(state)}
              onClick={() => void onMakePlan()}
            >
              {state.plan_status === "ready" ? "계획 준비됨" : "계획 만들기"}
            </button>
            {state.plan_status === "failed" ? (
              <p className="concept-panel__error" role="alert">
                계획 생성에 실패했습니다. 다시 시도하세요.
              </p>
            ) : null}
          </section>
        ) : null}
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
        <div className="concept-panel__export">
          <button
            type="button"
            disabled={pending}
            onClick={() => void onCopy()}
          >
            계획 복사
          </button>
          <button
            type="button"
            disabled={pending}
            onClick={() => void onDownload()}
          >
            Markdown 내려받기
          </button>
        </div>
        {exported?.warnings.length ? (
          <p className="concept-panel__notice" role="status">
            {exported.warnings.join(" ")}
          </p>
        ) : null}
        {exportNote ? (
          <p className="concept-panel__muted" role="status">
            {exportNote}
          </p>
        ) : null}
        {exported ? (
          <details className="concept-panel__exported">
            <summary>내보낼 문서 보기 (rev {exported.revision})</summary>
            <textarea readOnly value={exported.markdown} rows={12} />
          </details>
        ) : null}
        <p className="concept-panel__muted">
          방향 수정은 대화로도 됩니다. 선택도 내보내기도 실행 승인이 아닙니다.
        </p>
      </footer>
    </aside>
  );
}
