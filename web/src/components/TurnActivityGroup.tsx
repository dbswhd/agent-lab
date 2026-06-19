import type { TurnItem } from "../utils/turnItems";

type Props = {
  readonly items?: readonly TurnItem[];
  readonly running: boolean;
};

function itemLabel(item: TurnItem): string {
  if (item.kind === "tool")
    return item.doneAt ? `${item.tool} 완료` : `${item.tool} 실행 중`;
  if (item.kind === "error") return "오류";
  if (item.kind === "reasoning_summary") return "생각 요약";
  if (item.kind === "command") return "명령";
  if (item.kind === "file_change") return "파일 변경";
  if (item.kind === "activity") return "수행";
  return "최종 답변";
}

export function TurnActivityGroup({ items = [], running }: Props) {
  const activityItems = items.filter((item) => item.kind !== "final_output");
  if (activityItems.length === 0) return null;
  return (
    <details className="turn-activity" open={running || undefined}>
      <summary>
        <span>{running ? "수행 중" : "수행 기록"}</span>
        <span>{activityItems.length}</span>
      </summary>
      <div className="turn-activity__items">
        {activityItems.map((item) => (
          <div
            key={item.id}
            className={`turn-activity__item turn-activity__item--${item.kind}`}
          >
            <span className="turn-activity__kind">{itemLabel(item)}</span>
            {item.kind === "tool" ? (
              <div>
                {item.args ? <code>{item.args}</code> : null}
                {item.output ? <pre>{item.output}</pre> : null}
              </div>
            ) : (
              <span>{item.text}</span>
            )}
          </div>
        ))}
      </div>
    </details>
  );
}
