import { type ReactNode } from "react";

export function renderPlanInline(text: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  const re = /(\*\*([^*]+)\*\*|`([^`]+)`)/g;
  let last = 0;
  let m: RegExpExecArray | null;
  let k = 0;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) nodes.push(text.slice(last, m.index));
    const key = `i${k++}`;
    if (m[2]) nodes.push(<strong key={key}>{m[2]}</strong>);
    else if (m[3]) {
      nodes.push(
        <code key={key} className="plan-doc__code">
          {m[3]}
        </code>,
      );
    }
    last = m.index + m[0].length;
  }
  if (last < text.length) nodes.push(text.slice(last));
  return nodes.length ? nodes : [text];
}

export function PlanDocRefs({
  refs,
  onRefClick,
}: {
  refs: number[];
  onRefClick?: (line: number) => void;
}) {
  if (!refs.length) return null;
  return (
    <span className="plan-doc__refs">
      {refs.map((line) =>
        onRefClick ? (
          <button
            key={line}
            type="button"
            className="plan-doc__ref plan-doc__ref--link"
            title={`대화 L${line}로 이동`}
            onClick={() => onRefClick(line)}
          >
            L{line}
          </button>
        ) : (
          <span key={line} className="plan-doc__ref">
            L{line}
          </span>
        ),
      )}
    </span>
  );
}
