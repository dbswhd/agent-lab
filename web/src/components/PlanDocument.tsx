import { useMemo } from "react";
import { renderPlanMarkdown } from "../utils/planMarkdown";

type Props = {
  planMd: string;
  onRefClick?: (lineNumber: number) => void;
  /** Hide ## 지금 실행 / roadmap blocks when the interactive panel shows them. */
  skipExecuteSections?: boolean;
};

export function PlanDocument({ planMd, onRefClick, skipExecuteSections }: Props) {
  const content = useMemo(
    () =>
      renderPlanMarkdown(planMd, onRefClick, { skipExecuteSections }),
    [planMd, onRefClick, skipExecuteSections],
  );

  return <div className="plan-doc-wrap">{content}</div>;
}
