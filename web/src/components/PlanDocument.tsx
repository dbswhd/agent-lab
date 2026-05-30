import { useMemo, type ReactNode } from "react";

/** All chat.jsonl line refs (optional space after L). */
const REF_PATTERN = /chat\.jsonl#L\s*(\d+)/gi;

type Props = {
  planMd: string;
  onRefClick?: (lineNumber: number) => void;
};

export function PlanDocument({ planMd, onRefClick }: Props) {
  const nodes = useMemo(() => {
    const out: ReactNode[] = [];
    let last = 0;
    REF_PATTERN.lastIndex = 0;
    let match: RegExpExecArray | null;
    while ((match = REF_PATTERN.exec(planMd)) !== null) {
      const [full, lineStr] = match;
      const start = match.index;
      if (start > last) {
        out.push(planMd.slice(last, start));
      }
      const lineNumber = Number(lineStr);
      if (onRefClick && lineNumber > 0) {
        out.push(
          <button
            key={`ref-${start}-${lineNumber}`}
            type="button"
            className="plan-ref-link"
            title={`대화 L${lineNumber}로 이동`}
            onClick={() => onRefClick(lineNumber)}
          >
            {full}
          </button>,
        );
      } else {
        out.push(full);
      }
      last = start + full.length;
    }
    if (last < planMd.length) {
      out.push(planMd.slice(last));
    }
    return out;
  }, [planMd, onRefClick]);

  return <pre className="plan-pre">{nodes}</pre>;
}
