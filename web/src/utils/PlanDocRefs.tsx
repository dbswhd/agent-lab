import { useLocale } from "../i18n/useLocale";

export function PlanDocRefs({
  refs,
  onRefClick,
}: {
  refs: number[];
  onRefClick?: (line: number) => void;
}) {
  const { msg } = useLocale();
  if (!refs.length) return null;
  return (
    <span className="plan-doc__refs">
      {refs.map((line) =>
        onRefClick ? (
          <button
            key={line}
            type="button"
            className="plan-doc__ref plan-doc__ref--link"
            title={msg.planRefGoToChat(line)}
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
