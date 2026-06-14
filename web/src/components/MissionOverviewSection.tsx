import type { MissionOverviewView } from "../utils/missionOverviewView";
import { missionCircuitBreakerHint } from "../utils/missionPauseCopy";

type Props = {
  view: MissionOverviewView;
  ko: boolean;
  onFocusBlock?: (objectionId: string, actionIndex?: number) => void;
  /** Inspector sidebar (default) or compact Work tab strip */
  variant?: "inspector" | "work";
};

/** 언더스코어 enum → 사람이 읽기 좋은 짧은 레이블 (ko/en 분리) */
const PHASE_LABELS_KO: Record<string, string> = {
  MISSION_DEFINE: "정의 중",
  MISSION_DONE: "완료",
  MISSION_PAUSED: "일시정지",
  PLAN_GATE: "게이트",
  PLAN_REJECT: "반려됨",
  REPAIR: "수정 중",
  VERIFY: "검증 중",
  DISCUSS: "토론 중",
};

const PHASE_LABELS_EN: Record<string, string> = {
  MISSION_DEFINE: "Defining",
  MISSION_DONE: "Done",
  MISSION_PAUSED: "Paused",
  PLAN_GATE: "Gate",
  PLAN_REJECT: "Rejected",
  REPAIR: "Repair",
  VERIFY: "Verify",
  DISCUSS: "Discuss",
};

function phaseLabel(phase: string | null, ko: boolean): string {
  if (!phase) return "";
  const map = ko ? PHASE_LABELS_KO : PHASE_LABELS_EN;
  return map[phase] ?? phase.replace(/_/g, " ").toLowerCase();
}

function phaseBadgeClassWork(phase: string | null): string {
  if (!phase) return "work-mission__phase";
  if (phase === "MISSION_DONE")
    return "work-mission__phase work-mission__phase--done";
  if (phase === "MISSION_PAUSED" || phase === "PLAN_REJECT") {
    return "work-mission__phase work-mission__phase--warn";
  }
  return "work-mission__phase work-mission__phase--active";
}

function phaseBadgeClass(phase: string | null): string {
  if (!phase) return "ctx-mission__phase";
  if (phase === "MISSION_DONE")
    return "ctx-mission__phase ctx-mission__phase--done";
  if (phase === "MISSION_PAUSED" || phase === "PLAN_REJECT") {
    return "ctx-mission__phase ctx-mission__phase--warn";
  }
  if (phase === "REPAIR" || phase === "VERIFY") {
    return "ctx-mission__phase ctx-mission__phase--active";
  }
  return "ctx-mission__phase ctx-mission__phase--active";
}

function WorkMissionOverview({
  view,
  ko,
  onFocusBlock,
}: Omit<Props, "variant">) {
  return (
    <section className="work-mission" data-testid="work-mission-overview">
      <div className="work-mission__head">
        <span className="work-mission__title">{ko ? "미션" : "Mission"}</span>
        {view.autonomousActive ? (
          <span className="work-mission__auto">
            {ko ? "자율 구간" : "Autonomous"}
          </span>
        ) : null}
        {view.phase ? (
          <span className={phaseBadgeClassWork(view.phase)}>
            {phaseLabel(view.phase, ko)}
          </span>
        ) : null}
      </div>
      {view.goalText ? (
        <p className="work-mission__goal">{view.goalText}</p>
      ) : null}
      <dl className="work-mission__facts">
        {view.nextActionIndex != null ? (
          <>
            <dt>{ko ? "다음" : "Next"}</dt>
            <dd>
              #{view.nextActionIndex}
              {view.nextActionWhat ? ` · ${view.nextActionWhat}` : ""}
            </dd>
          </>
        ) : null}
        {view.circuitBreaker ? (
          <>
            <dt>{ko ? "차단" : "Breaker"}</dt>
            <dd className="work-mission__danger">
              {missionCircuitBreakerHint(view.circuitBreakerReason, ko)}
            </dd>
          </>
        ) : null}
        {view.phase === "MISSION_PAUSED" && view.resumePhase ? (
          <>
            <dt>{ko ? "재개" : "Resume"}</dt>
            <dd>{view.resumePhase}</dd>
          </>
        ) : null}
        {view.pendingCount > 0 ? (
          <>
            <dt>{ko ? "대기" : "Queue"}</dt>
            <dd>{view.pendingCount}</dd>
          </>
        ) : null}
        {view.openBlocks.length > 0 ? (
          <>
            <dt>BLOCK</dt>
            <dd>{view.openBlocks.length}</dd>
          </>
        ) : null}
      </dl>
      {view.openBlocks.length > 0 ? (
        <ul className="work-mission__blocks">
          {view.openBlocks.slice(0, 3).map((block) => (
            <li key={block.id}>
              <button
                type="button"
                className="work-mission__block-btn"
                onClick={() =>
                  onFocusBlock?.(block.id, block.plan_action_index)
                }
              >
                {block.body.trim() || block.id}
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}

/** Inspector Overview — mission goal · phase · next action · BLOCK. */
export function MissionOverviewSection({
  view,
  ko,
  onFocusBlock,
  variant = "inspector",
}: Props) {
  if (!view.enabled && !view.goalText) return null;

  if (variant === "work") {
    return (
      <WorkMissionOverview view={view} ko={ko} onFocusBlock={onFocusBlock} />
    );
  }

  return (
    <section className="ctx-section ctx-mission">
      <div className="ctx-section__label">
        {ko ? "미션" : "Mission"}
        {view.phase ? (
          <span className={phaseBadgeClass(view.phase)}>
            {phaseLabel(view.phase, ko)}
          </span>
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
