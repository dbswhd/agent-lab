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

  if (!hasPlan) {
    return (
      <div className="workspace-empty-state workspace-panel--work">
        plan.md가 아직 없습니다. Transcript에서 토론을 시작하거나 「지금 정리」를
        사용하세요.
      </div>
    );
  }

  return (
    <div className="plan-tab-cluster workspace-document-panel workspace-document-panel--flat">
        <div className="workspace-document-panel__header workspace-document-panel__header--work">
          <strong>Work</strong>
          <span>Plan · review · execute</span>
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

        <PlanDocument
          planMd={planMd}
          skipExecuteSections
          onRefClick={onPlanRefClick}
        />

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
    </div>
  );
}
