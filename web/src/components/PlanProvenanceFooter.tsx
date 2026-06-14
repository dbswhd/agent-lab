import { extractPlanChatRefs } from "../utils/planProvenance";
import { useLocale } from "../i18n/useLocale";

const MAX_VISIBLE = 5;

type Props = {
  planMd: string;
  onRefClick?: (line: number) => void;
};

export function PlanProvenanceFooter({ planMd, onRefClick }: Props) {
  const { msg } = useLocale();
  const refs = extractPlanChatRefs(planMd);
  if (!refs.length || !onRefClick) return null;

  const visible = refs.slice(0, MAX_VISIBLE);
  const hidden = refs.length - visible.length;

  return (
    <div className="plan-provenance-footer" role="navigation" aria-label={msg.planProvenanceTitle}>
      <span className="plan-provenance-footer__label">{msg.planProvenanceTitle}</span>
      <div className="plan-provenance-footer__links">
        {visible.map((line) => (
          <button
            key={line}
            type="button"
            className="plan-doc__ref plan-doc__ref--link"
            title={msg.planRefGoToChat(line)}
            onClick={() => onRefClick(line)}
          >
            L{line}
          </button>
        ))}
        {hidden > 0 ? (
          <span className="plan-provenance-footer__more">+{hidden}</span>
        ) : null}
      </div>
    </div>
  );
}
