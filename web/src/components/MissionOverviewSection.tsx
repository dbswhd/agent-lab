import type { MissionOverviewView } from "../utils/missionOverviewView";

type Props = {
  view: MissionOverviewView;
  ko: boolean;
  onFocusBlock?: (objectionId: string, actionIndex?: number) => void;
};

function phaseBadgeClass(phase: string | null): string {
  if (!phase) return "ctx-mission__phase";
  if (phase === "MISSION_DONE") return "ctx-mission__phase ctx-mission__phase--done";
  if (phase === "MISSION_PAUSED" || phase === "PLAN_REJECT") {
    return "ctx-mission__phase ctx-mission__phase--warn";
  }
  if (phase === "REPAIR" || phase === "VERIFY") {
    return "ctx-mission__phase ctx-mission__phase--active";
  }
  return "ctx-mission__phase ctx-mission__phase--active";
}

/** Inspector Overview — mission goal · phase · next action · BLOCK. */
export function MissionOverviewSection({ view, ko, onFocusBlock }: Props) {
  if (!view.enabled && !view.goalText) return null;

  return (
    <section className="ctx-section ctx-mission">
      <div className="ctx-section__label">
        {ko ? "미션" : "Mission"}
        {view.phase ? (
          <span className={phaseBadgeClass(view.phase)}>{view.phase}</span>
        ) : null}
      </div>

      {view.goalText ? (
        <p className="ctx-goal">{view.goalText}</p>
      ) : (
        <p className="ctx-overview__empty">
          {ko ? "미션 목표 없음" : "No mission goal"}
        </p>
      )}

      <dl className="ctx-mission__facts">
        {view.nextActionIndex != null ? (
          <>
            <dt>{ko ? "다음 action" : "Next action"}</dt>
            <dd>
              #{view.nextActionIndex}
              {view.nextActionWhat ? ` — ${view.nextActionWhat}` : ""}
              {view.pendingCount > 1
                ? ` (${ko ? "대기" : "queued"} ${view.pendingCount})`
                : ""}
            </dd>
          </>
        ) : null}
        {view.verifiedStatus ? (
          <>
            <dt>{ko ? "Verified loop" : "Verified loop"}</dt>
            <dd>{view.verifiedStatus}</dd>
          </>
        ) : null}
        {view.circuitBreaker ? (
          <>
            <dt>{ko ? "차단" : "Breaker"}</dt>
            <dd className="ctx-mission__danger">
              {view.circuitBreakerReason ?? "circuit_breaker"}
            </dd>
          </>
        ) : null}
        {view.pauseReason ? (
          <>
            <dt>{ko ? "일시정지" : "Paused"}</dt>
            <dd>{view.pauseReason}</dd>
          </>
        ) : null}
      </dl>

      {view.openBlocks.length > 0 ? (
        <ul className="ctx-mission__blocks">
          {view.openBlocks.slice(0, 4).map((block) => (
            <li key={block.id}>
              <button
                type="button"
                className="ctx-mission__block-btn"
                onClick={() =>
                  onFocusBlock?.(block.id, block.plan_action_index)
                }
              >
                <span className="ctx-mission__block-tag">BLOCK</span>
                <span className="ctx-mission__block-body">
                  {block.body.trim() || block.id}
                </span>
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <p className="ctx-overview__empty">
          {ko ? "open BLOCK 없음" : "No open BLOCK"}
        </p>
      )}
    </section>
  );
}
