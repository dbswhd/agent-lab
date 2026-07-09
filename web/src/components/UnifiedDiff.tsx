import { useEffect, useMemo, useRef } from "react";
import { parseUnifiedDiff } from "../utils/unifiedDiff";

type Props = {
  diff: string | undefined;
  activeHunkId?: string;
};

export function UnifiedDiff({ diff, activeHunkId }: Props) {
  const bodyRef = useRef<HTMLDivElement>(null);
  const { rows, hunks } = useMemo(() => parseUnifiedDiff(diff), [diff]);

  useEffect(() => {
    if (!activeHunkId || !bodyRef.current) return;
    const hunk = hunks.find((h) => h.id === activeHunkId);
    if (!hunk) return;
    const el = bodyRef.current.querySelector(`[data-row-id="${hunk.rowId}"]`);
    if (el instanceof HTMLElement) {
      el.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }
  }, [activeHunkId, hunks]);

  if (!rows.length) return null;

  return (
    <div className="exec-diff exec-diff--unified">
      <div ref={bodyRef} className="exec-diff__body exec-diff__body--unified">
        {rows.map((row) => {
          const isActiveHunk = Boolean(activeHunkId) && row.hunkId === activeHunkId;

          if (row.kind === "meta" || row.kind === "header") {
            return (
              <pre
                key={row.id}
                data-row-id={row.id}
                data-hunk-id={row.hunkId ?? undefined}
                className={`diff-unified-line diff-unified-line--meta${
                  isActiveHunk ? " diff-unified-line--active-hunk" : ""
                }`}
              >
                {row.left}
              </pre>
            );
          }

          if (row.kind === "pair" && row.leftSegments && row.rightSegments) {
            return (
              <div
                key={row.id}
                data-row-id={row.id}
                data-hunk-id={row.hunkId ?? undefined}
                className={`diff-unified-pair${
                  isActiveHunk ? " diff-unified-pair--active-hunk" : ""
                }`}
              >
                <pre className="diff-unified-line diff-unified-line--del">
                  <span className="diff-gutter diff-gutter--del">&minus;</span>
                  {row.leftSegments.map((segment, index) => (
                    <span
                      key={index}
                      className={segment.changed ? "diff-word diff-word--del" : undefined}
                    >
                      {segment.text}
                    </span>
                  ))}
                </pre>
                <pre className="diff-unified-line diff-unified-line--add">
                  <span className="diff-gutter diff-gutter--add">+</span>
                  {row.rightSegments.map((segment, index) => (
                    <span
                      key={index}
                      className={segment.changed ? "diff-word diff-word--add" : undefined}
                    >
                      {segment.text}
                    </span>
                  ))}
                </pre>
              </div>
            );
          }

          const content =
            row.kind === "add" ? row.right : row.kind === "del" ? row.left : row.left;

          return (
            <pre
              key={row.id}
              data-row-id={row.id}
              data-hunk-id={row.hunkId ?? undefined}
              className={`diff-unified-line diff-unified-line--${row.kind}${
                isActiveHunk ? " diff-unified-line--active-hunk" : ""
              }`}
            >
              {content}
            </pre>
          );
        })}
      </div>
    </div>
  );
}
