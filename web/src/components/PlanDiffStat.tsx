import { parseDiffStat } from "../utils/diffStatFormat";

type Props = {
  text: string;
};

/** Rebuilt diff-stat. Logic (parseDiffStat) preserved; new `.diffstat` classes. */
export function PlanDiffStat({ text }: Props) {
  const parsed = parseDiffStat(text);
  if (!parsed) {
    return <pre className="diffstat diffstat--raw">{text}</pre>;
  }

  return (
    <div className="diffstat">
      {parsed.files.map((row) => (
        <div key={row.path} className="diffstat__file">
          <span className="diffstat__path" title={row.path}>
            {row.path}
          </span>
          <span className="diffstat__counts">
            <span className="diffstat__add">+{row.adds}</span>
            <span className="diffstat__del">-{row.dels}</span>
          </span>
        </div>
      ))}
      {parsed.summary ? (
        <p className="diffstat__summary">{parsed.summary}</p>
      ) : null}
    </div>
  );
}
