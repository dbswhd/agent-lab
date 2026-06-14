import type { MissionBoardPayload } from "../api/client";

type Props = {
  board: MissionBoardPayload | null | undefined;
  ko?: boolean;
};

function goalLabel(
  link: MissionBoardPayload["goal_chain"][number],
  ko: boolean,
): string {
  if (link.kind === "verified_loop.loop_goal") {
    return ko ? "검증 목표" : "Verified goal";
  }
  if (link.kind === "session_goal") {
    return ko ? "세션 목표" : "Session goal";
  }
  if (link.kind === "plan_action") {
    const title = link.title?.trim();
    if (title) return title;
    return ko ? `액션 #${link.index ?? "?"}` : `Action #${link.index ?? "?"}`;
  }
  return link.kind.replace(/_/g, " ");
}

/** MB-1 — goal chain + lane checkout (Paperclip task tree, not org chart). */
export function MissionBoardStrip({ board, ko = true }: Props) {
  const chain = board?.goal_chain ?? [];
  const checkout = board?.checkout;
  if (chain.length === 0 && !checkout) return null;

  return (
    <section className="mission-board-strip" data-testid="mission-board-strip">
      {chain.length > 0 ? (
        <ol
          className="mission-board-strip__chain"
          aria-label={ko ? "목표 경로" : "Goal chain"}
        >
          {chain.map((link, i) => (
            <li
              key={`${link.kind}-${link.index ?? i}`}
              className="mission-board-strip__link"
            >
              {goalLabel(link, ko)}
            </li>
          ))}
        </ol>
      ) : null}
      {checkout?.lane ? (
        <p className="mission-board-strip__checkout">
          <span className="mission-board-strip__checkout-label">
            {ko ? "체크아웃" : "Checkout"}
          </span>
          <span className="mission-board-strip__checkout-lane">
            {checkout.lane}
          </span>
          {checkout.action_index != null ? (
            <span className="mission-board-strip__checkout-meta">
              #{checkout.action_index}
            </span>
          ) : null}
        </p>
      ) : null}
    </section>
  );
}
