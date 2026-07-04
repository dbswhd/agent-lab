import type { ComponentProps, ReactNode } from "react";
import type { AgentHealthRow, AgentOption } from "../api/client";
import type { useLocale } from "../i18n/useLocale";
import type { PendingFile } from "./ChatComposer";
import { ChatComposer } from "./ChatComposer";
import { ComposerEventStack } from "./ComposerEventStack";
import { ComposerPreflightBar } from "./ComposerPreflightBar";
import { ReadinessComposerBar } from "./ReadinessComposerBar";
import { SlashCommandDivider } from "./SlashCommandDivider";
import type { ReadinessResponse } from "../api/client";
import { shouldShowSendReceiptOnChatTab } from "../utils/sendReceipt";
import { DEMO_PREFLIGHT_AGENTS } from "../utils/tweaksDemoFixtures";
import { sortAgentIds } from "../utils/agentOrder";

type ComposerEventStackProps = ComponentProps<typeof ComposerEventStack>;

type Props = {
  show: boolean;
  tweaksPreflightDemo: boolean;
  recoveryItemsLength: number;
  readiness: ReadinessResponse | null;
  healthAgents: AgentHealthRow[];
  selected: string[];
  clarifierQuestions: string[] | null;
  clarifierInterview: {
    questions?: { id?: string; category?: string; prompt?: string }[];
    plan_mode?: boolean;
  } | null;
  planWorkflowActive: boolean;
  planWorkflowPhase?: string;
  longRunning: boolean;
  running: boolean;
  onStop: () => void;
  sessionId: string | null;
  eventStack: ComposerEventStackProps | null;
  sendReceipt: string | null;
  sendReceiptRaw: string | undefined;
  composerClassName?: string;
  text: string;
  onTextChange: (value: string) => void;
  onSend: () => void;
  slashCommands: ComponentProps<typeof ChatComposer>["slashCommands"];
  onSlashExecute: ComponentProps<typeof ChatComposer>["onSlashExecute"];
  composerInputLocked: boolean;
  composerSendLocked: boolean;
  composerPlaceholder: string;
  pendingFiles: PendingFile[];
  onFilesAdd: (files: FileList | File[]) => void;
  onFileRemove: (id: string) => void;
  composerObjectionNotice: ComponentProps<
    typeof ChatComposer
  >["objectionNotice"];
  onFocusObjection: (id: string, actionIndex?: number) => void;
  turnHint?: string | null;
  costHint?: string | null;
  locale: ReturnType<typeof useLocale>["locale"];
  roomPresets: ComponentProps<typeof ChatComposer>["roomPresets"];
  roomPreset: string | null;
  onRoomPresetSelect: (id: string) => void;
  agents: AgentOption[];
  onOpenModelPicker: () => void;
  choicePopover: ReactNode;
  authPopover: ReactNode;
  authPickerPopover: ReactNode;
  modelPopover: ReactNode;
  commandHint: string | null;
};

export function RoomChatComposerShell({
  show,
  tweaksPreflightDemo,
  recoveryItemsLength,
  readiness,
  healthAgents,
  selected,
  clarifierQuestions,
  clarifierInterview,
  planWorkflowActive,
  planWorkflowPhase,
  longRunning,
  running,
  onStop,
  sessionId,
  eventStack,
  sendReceipt,
  sendReceiptRaw,
  composerClassName,
  text,
  onTextChange,
  onSend,
  slashCommands,
  onSlashExecute,
  composerInputLocked,
  composerSendLocked,
  composerPlaceholder,
  pendingFiles,
  onFilesAdd,
  onFileRemove,
  composerObjectionNotice,
  onFocusObjection,
  turnHint,
  costHint,
  locale,
  roomPresets,
  roomPreset,
  onRoomPresetSelect,
  agents,
  onOpenModelPicker,
  choicePopover,
  authPopover,
  authPickerPopover,
  modelPopover,
  commandHint,
}: Props) {
  if (!show) return null;

  return (
    <>
      {tweaksPreflightDemo ? (
        <ComposerPreflightBar
          agents={DEMO_PREFLIGHT_AGENTS}
          selected={["cursor"]}
        />
      ) : recoveryItemsLength === 0 ? (
        <>
          <ReadinessComposerBar readiness={readiness} />
          <ComposerPreflightBar agents={healthAgents} selected={selected} />
        </>
      ) : null}
      <div className="composer-wrap">
        {clarifierQuestions &&
        clarifierQuestions.length > 0 &&
        !(
          planWorkflowActive &&
          (planWorkflowPhase === "CLARIFY" || planWorkflowPhase === "INTAKE")
        ) ? (
          <div
            className="clarifier-banner"
            role="region"
            aria-label="확인 질문"
          >
            <strong className="clarifier-banner__title">
              {clarifierInterview?.plan_mode ? "계획 확인 질문" : "확인 질문"}
            </strong>
            <ul>
              {(clarifierInterview?.questions?.length
                ? clarifierInterview.questions
                : clarifierQuestions.map((prompt) => ({
                    id: prompt,
                    prompt,
                  }))
              ).map((q) => (
                <li key={q.id ?? q.prompt}>
                  {"category" in q && q.category ? (
                    <span className="clarifier-banner__category">
                      {q.category}
                    </span>
                  ) : null}
                  {q.prompt ?? ""}
                </li>
              ))}
            </ul>
            <p className="clarifier-banner__hint">
              답을 메시지에 포함해 다시 내면 에이전트가 시작됩니다.
            </p>
          </div>
        ) : null}

        {longRunning && running ? (
          <div className="room-run-status" role="status">
            <span className="room-run-status__hint">장시간 실행 중...</span>
            <button
              type="button"
              className="mac-btn-secondary mac-btn-secondary--compact"
              onClick={onStop}
            >
              답변 중지
            </button>
          </div>
        ) : null}

        {sessionId && eventStack ? (
          <ComposerEventStack {...eventStack} />
        ) : null}

        {sendReceipt &&
        shouldShowSendReceiptOnChatTab(sendReceipt, sendReceiptRaw) ? (
          <div className="composer-send-receipt" role="status">
            {sendReceipt}
          </div>
        ) : null}

        <ChatComposer
          className={composerClassName}
          value={text}
          onChange={onTextChange}
          onSend={onSend}
          slashCommands={slashCommands}
          onSlashExecute={onSlashExecute}
          disabled={composerInputLocked}
          sendDisabled={composerSendLocked}
          placeholder={composerPlaceholder}
          showModeChipHint={false}
          running={running}
          onStop={onStop}
          files={pendingFiles}
          onFilesAdd={onFilesAdd}
          onFileRemove={onFileRemove}
          objectionNotice={composerObjectionNotice}
          onFocusObjection={onFocusObjection}
          turnHint={turnHint}
          costHint={costHint}
          locale={locale}
          sessionId={sessionId}
          roomPresets={roomPresets}
          roomPreset={roomPreset}
          onRoomPresetSelect={onRoomPresetSelect}
          activeModels={sortAgentIds(selected)
            .map((id) => agents.find((agent) => agent.id === id))
            .filter((agent): agent is AgentOption => Boolean(agent))}
          onOpenModelPicker={onOpenModelPicker}
          choicePopover={choicePopover}
          authPopover={authPopover}
          authPickerPopover={authPickerPopover}
          modelPopover={modelPopover}
        />

        {commandHint ? (
          <SlashCommandDivider
            text={commandHint}
            className="composer-slash-divider"
          />
        ) : null}
      </div>
    </>
  );
}
