import type { PlanExecutionRecord, SessionDetail } from "../api/client";
import type { PlanMetaView } from "../utils/planMeta";
import type { StoredPlanAction } from "../utils/planExecuteHistory";
import type { RoomTasksPayload } from "../api/client";
import type { ConsensusDryRunProposal } from "./ConsensusDryRunGateBar";
import { PlanDocument } from "./PlanDocument";
import { PlanTabToolbar } from "./PlanTabToolbar";
import { PlanExecutePanel } from "./PlanExecutePanel";
import { ExecuteQueueBar } from "./ExecuteQueueBar";
import { ConsensusDryRunGateBar } from "./ConsensusDryRunGateBar";
import { CollapsibleGlassPanel } from "./CollapsibleGlassPanel";
import {
  WorkStatusBar,
  resolveWorkPhase,
} from "./WorkStatusBar";
import type { PlanRefWarningsView } from "../utils/planRefWarnings";

function statusLabel(activePending: PlanExecutionRecord | null | undefined): string {
  if (!activePending) return "Plan ready";
  if (activePending.status === "merge_conflict") return "Merge conflict";
  if (activePending.status === "merged") return "Verified";
  if (activePending.status === "blocked_isolation") return "Blocked";
  return "Review pending";
}

function executionHistory(
  run: SessionDetail["run"] | null | undefined,
): PlanExecutionRecord[] {
  const rows = Array.isArray(run?.executions)
    ? (run.executions as PlanExecutionRecord[])
    : [];
  return rows.slice(-5).reverse();
}

type Props = {
  sessionId: string;
  session: SessionDetail | null;
  planMd: string;
  planMeta: PlanMetaView;
  planRefWarnings: PlanRefWarningsView;
  planAfterSend: boolean;
  onPlanAfterSendChange: (on: boolean) => void;
  synthesizing: boolean;
  running: boolean;
  runBusy: boolean;
  onSynthesizeNow: () => void;
  hasPendingExecution: boolean;
  consensusProposal: ConsensusDryRunProposal | null;
  consensusGateBusy: boolean;
  executeBusy: boolean;
  onConsensusDryRun: () => void;
  onDismissConsensus: () => void;
  onApproveExecute: () => void;
  onRejectExecute: () => void;
  onPlanRefClick: (line: number) => void;
  onFocusTask: (taskId: string) => void;
  onFocusObjection: (id: string, actionIndex?: number) => void;
  onSessionUpdated: () => void;
  roomTasks: RoomTasksPayload | null;
  cursorReady: boolean;
  storedActions: StoredPlanAction[];
  activePending: PlanExecutionRecord | null | undefined;
};

export function WorkPanel({
  sessionId,
  session,
  planMd,
  planMeta,
  planRefWarnings,
  planAfterSend,
  onPlanAfterSendChange,
  synthesizing,
  running,
  runBusy,
  onSynthesizeNow,
  hasPendingExecution,
  consensusProposal,
  consensusGateBusy,
  executeBusy,
  onConsensusDryRun,
  onDismissConsensus,
  onApproveExecute,
  onRejectExecute,
  onPlanRefClick,
  onFocusTask,
  onFocusObjection,
  onSessionUpdated,
  roomTasks,
  cursorReady,
  storedActions,
  activePending,
}: Props) {
  const hasPlan = Boolean(planMd.trim());
  const phase = resolveWorkPhase({
    hasPlan,
    hasPendingExecution,
    hasDryRunDiff: consensusProposal != null || Boolean(activePending?.diff),
    pendingAgreement: Boolean(planMeta.pendingAgreement),
  });
  const history = executionHistory(session?.run);
  const selectedStatus = statusLabel(activePending);

  if (!hasPlan) {
    return (
      <div className="workspace-empty-state workspace-panel--work">
        plan.md가 아직 없습니다. Transcript에서 토론을 시작하거나 「지금 정리」를
        사용하세요.
      </div>
    );
  }

  return (
    <div className="work-panel plan-tab-cluster workspace-document-panel workspace-document-panel--flat">
        <div className="work-panel__header workspace-document-panel__header workspace-document-panel__header--work">
          <div>
            <strong>Work</strong>
            <span>실행 판단 · diff review · merge verify</span>
          </div>
          <div className="work-panel__badges" aria-label="Work 상태">
            <span className="work-panel__phase-badge">{selectedStatus}</span>
            {planMeta.pendingAgreement ? (
              <span className="work-panel__phase-badge work-panel__phase-badge--warn">
                stale plan
              </span>
            ) : null}
            {hasPendingExecution ? (
              <span className="work-panel__phase-badge work-panel__phase-badge--action">
                approval
              </span>
            ) : null}
          </div>
        </div>

        <WorkStatusBar phase={phase} planMeta={planMeta} hasPlan={hasPlan} />

        <PlanTabToolbar
          planAfterSend={planAfterSend}
          onPlanAfterSendChange={onPlanAfterSendChange}
          synthesizing={synthesizing}
          running={running}
          disabled={runBusy}
          onSynthesizeNow={onSynthesizeNow}
          planMeta={planMeta}
        />

        {planMeta.pendingAgreement ? (
          <div className="plan-meta-bar plan-meta-bar--sync_failed work-panel__alert">
            <p className="plan-meta-bar__line">{planMeta.freshnessLabel}</p>
            <button
              type="button"
              className="room-plan-btn room-plan-btn--accent"
              disabled={running || synthesizing}
              onClick={onSynthesizeNow}
            >
              {synthesizing ? "정리 중…" : "다시 정리"}
            </button>
          </div>
        ) : null}

        {activePending ? (
          <ExecuteQueueBar
            pending={activePending}
            storedActions={storedActions}
            busy={executeBusy}
            disabled={running || synthesizing || runBusy}
            onApprove={onApproveExecute}
            onReject={onRejectExecute}
          />
        ) : null}

        {consensusProposal ? (
          <ConsensusDryRunGateBar
            proposal={consensusProposal}
            busy={consensusGateBusy || executeBusy}
            disabled={running || synthesizing || runBusy}
            onDryRun={onConsensusDryRun}
            onOpenPlan={() => {}}
            onDismiss={onDismissConsensus}
          />
        ) : null}

        {planRefWarnings.bannerText ? (
          <CollapsibleGlassPanel
            className="plan-ref-warn-panel"
            title="ref 경고"
            summary={planRefWarnings.bannerText}
            variant="warn"
            defaultOpen={false}
          >
            <p className="plan-ref-warn-panel__text">
              {planRefWarnings.bannerText}
            </p>
          </CollapsibleGlassPanel>
        ) : null}

        <section className="work-panel__lane work-panel__lane--review" aria-label="Review lane">
          <div className="work-panel__lane-head">
            <div>
              <h2>Action & Review</h2>
              <p>지금 실행할 action을 고르고 dry-run diff를 승인·거부·재작업합니다.</p>
            </div>
          </div>
          <PlanExecutePanel
            sessionId={sessionId}
            run={session?.run}
            linkedTasks={roomTasks?.tasks}
            cursorReady={cursorReady}
            disabled={running || synthesizing || runBusy}
            onChatRefClick={onPlanRefClick}
            onFocusTask={onFocusTask}
            onFocusObjection={onFocusObjection}
            onUpdated={onSessionUpdated}
          />
        </section>

        {history.length > 0 ? (
          <section className="work-panel__history" aria-label="Execution history">
            <div className="work-panel__lane-head">
              <h2>Execution History</h2>
            </div>
            <ul>
              {history.map((execution) => (
                <li key={execution.id ?? `${execution.action_index}-${execution.status}`}>
                  <span className="work-panel__history-status">{execution.status}</span>
                  <span>{execution.exec_branch ?? execution.action_key ?? `#${execution.action_index ?? "?"}`}</span>
                  {execution.merge?.commit_sha ? (
                    <code>{execution.merge.commit_sha.slice(0, 7)}</code>
                  ) : null}
                </li>
              ))}
            </ul>
          </section>
        ) : null}

        <details className="work-panel__evidence" open={false}>
          <summary>Plan Evidence</summary>
          <PlanDocument
            planMd={planMd}
            skipExecuteSections
            onRefClick={onPlanRefClick}
          />
        </details>
    </div>
  );
}
