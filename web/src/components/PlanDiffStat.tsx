import { parseDiffStat } from "../utils/diffStatFormat";

type Props = {
  text: string;
};

export function PlanDiffStat({ text }: Props) {
  const parsed = parseDiffStat(text);
  if (!parsed) {
    return <pre className="plan-diff-stat plan-diff-stat--raw">{text}</pre>;
  }

  return (
    <div className="plan-diff-stat">
      {parsed.files.map((row) => (
        <div key={row.path} className="plan-diff-stat__file">
          <span className="plan-diff-stat__path" title={row.path}>
            {row.path}
          </span>
          <span className="plan-diff-stat__counts">
            <span className="plan-diff-stat__add">+{row.adds}</span>
            <span className="plan-diff-stat__del">-{row.dels}</span>
          </span>
        </div>
      ))}
      {parsed.summary ? (
        <p className="plan-diff-stat__summary">{parsed.summary}</p>
      ) : null}
    </div>
  );
}
