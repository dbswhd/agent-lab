import { PlanDocRefs } from "./PlanDocRefs";
import { renderPlanInline } from "./planDocInline";

export function PlanMarkdownBody({
  text,
  refs,
  onRefClick,
}: {
  text: string;
  refs: number[];
  onRefClick?: (line: number) => void;
}) {
  return (
    <span className="plan-doc__text">
      {renderPlanInline(text)}
      <PlanDocRefs refs={refs} onRefClick={onRefClick} />
    </span>
  );
}
