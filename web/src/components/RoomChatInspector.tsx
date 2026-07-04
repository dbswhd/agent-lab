import type {
  AgentHealthRow,
  PlanExecutionRecord,
  SessionDetail,
} from "../api/client";
import type { useLocale } from "../i18n/useLocale";
import type { GoalLoopView } from "../utils/goalLoopView";
import type { PlanMetaView } from "../utils/planMeta";
import type { RightPanelMode } from "../utils/workspaceTabs";
import { BackgroundTasksPanel } from "./BackgroundTasksPanel";
import { ContextOverviewPanel } from "./ContextOverviewPanel";
import { DiffToolPanel } from "./DiffToolPanel";
import { PreviewPanel } from "./PreviewPanel";
import { ShellPortal } from "./ShellPortal";
import { TerminalPanel } from "./TerminalPanel";
import { WorkbenchPanel } from "./WorkbenchPanel";
import { WorkspaceFilesPanel } from "./WorkspaceFilesPanel";

type Props = {
  isNew: boolean;
  inspectorOpen: boolean;
  rightPanelMode: RightPanelMode;
  locale: ReturnType<typeof useLocale>["locale"];
  workbenchPanelWidth: number;
  onWidthChange: (width: number) => void;
  onWidthCommit: (width: number) => void;
  onClose: () => void;
  session: SessionDetail | null;
  sessionId: string | null;
  healthAgents: AgentHealthRow[];
  goalView: GoalLoopView;
  planMeta: PlanMetaView;
  onFocusObjection: (id: string, actionIndex?: number) => void;
  planExecutions: readonly PlanExecutionRecord[];
  filesFocusPath: string | null;
  filesFocusRevision: number;
};

/** Right workbench inspector — extracted from RoomChat (F9). */
export function RoomChatInspector({
  isNew,
  inspectorOpen,
  rightPanelMode,
  locale,
  workbenchPanelWidth,
  onWidthChange,
  onWidthCommit,
  onClose,
  session,
  sessionId,
  healthAgents,
  goalView,
  planMeta,
  onFocusObjection,
  planExecutions,
  filesFocusPath,
  filesFocusRevision,
}: Props) {
  if (isNew || !inspectorOpen) return null;

  return (
    <ShellPortal>
      <WorkbenchPanel
        mode={rightPanelMode}
        locale={locale}
        open={inspectorOpen}
        width={workbenchPanelWidth}
        onWidthChange={onWidthChange}
        onWidthCommit={onWidthCommit}
        onClose={onClose}
      >
        {rightPanelMode === "overview" && session ? (
          <ContextOverviewPanel
            session={session}
            sessionId={sessionId}
            healthAgents={healthAgents}
            goalView={goalView}
            planMeta={planMeta}
            onFocusObjection={onFocusObjection}
          />
        ) : null}
        {rightPanelMode === "background" && sessionId ? (
          <BackgroundTasksPanel sessionId={sessionId} />
        ) : null}
        {rightPanelMode === "diff" ? (
          <DiffToolPanel executions={planExecutions} />
        ) : null}
        {rightPanelMode === "files" && sessionId ? (
          <WorkspaceFilesPanel
            sessionId={sessionId}
            focusPath={filesFocusPath}
            focusRevision={filesFocusRevision}
          />
        ) : null}
        {rightPanelMode === "preview" && sessionId ? (
          <PreviewPanel sessionId={sessionId} />
        ) : null}
        {rightPanelMode === "terminal" && sessionId ? (
          <TerminalPanel sessionId={sessionId} />
        ) : null}
      </WorkbenchPanel>
    </ShellPortal>
  );
}
