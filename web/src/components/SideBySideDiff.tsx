import { useEffect, useMemo, useRef } from "react";
import { parseSideBySideDiff } from "../utils/sideBySideDiff";

type Props = {
  diff: string | undefined;
  activeHunkId?: string;
};

export function SideBySideDiff({ diff, activeHunkId }: Props) {
  const bodyRef = useRef<HTMLDivElement>(null);
  const { rows, hunks } = useMemo(() => parseSideBySideDiff(diff), [diff]);

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
    <div className="exec-diff exec-diff--split">
      <div className="exec-diff__head exec-diff__head--split">
        <span>Before</span>
        <span>After</span>
      </div>
      <div ref={bodyRef} className="exec-diff__body exec-diff__body--split">
        {rows.map((row) => (
          <div
            key={row.id}
            data-row-id={row.id}
            data-hunk-id={row.hunkId ?? undefined}
            className={`diff-split-row diff-split-row--${row.kind}${
              row.hunkId === activeHunkId ? " diff-split-row--active-hunk" : ""
            }`}
          >
            {row.kind === "meta" || row.kind === "header" ? (
              <pre className="diff-split-cell diff-split-cell--full">
                {row.left}
              </pre>
            ) : row.kind === "pair" && row.leftSegments && row.rightSegments ? (
              <>
                <pre className="diff-split-cell diff-split-cell--left">
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
                <pre className="diff-split-cell diff-split-cell--right">
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
              </>
            ) : (
              <>
                <pre className="diff-split-cell diff-split-cell--left">
                  {row.left}
                </pre>
                <pre className="diff-split-cell diff-split-cell--right">
                  {row.right}
                </pre>
              </>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
