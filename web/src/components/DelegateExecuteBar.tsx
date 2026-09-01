import { useCallback, useEffect, useState } from "react";
import {
  fetchCommands,
  runSessionCommand,
  type PlanExecutionRecord,
  type SlashCommandRecord,
} from "../api/client";
import {
  buildDelegatePrompt,
  DELEGATE_ALLOWLIST_HINT,
  DELEGATE_TOOL_IDS,
  delegateActionLabel,
} from "../utils/externalHandoff";
import { isWorktreeExecution } from "../utils/planExecuteWorktree";
import { MacAlert } from "./MacAlert";
import { WorkPlanIcon } from "./WorkPlanIcon";

type Props = {
  sessionId: string;
  execution: PlanExecutionRecord;
  actionWhat?: string;
  actionWhere?: string;
  actionVerify?: string;
  runnerEnabled: boolean;
  allowlist: string[];
  disabled?: boolean;
  busy?: boolean;
  onUpdated: () => void;
};

type PendingDelegate = {
  toolId: string;
  toolLabel: string;
  prompt: string;
};

function runnableDelegateTools(
  commands: SlashCommandRecord[],
  allowlist: string[],
): SlashCommandRecord[] {
  const ids = new Set(Object.values(DELEGATE_TOOL_IDS));
  return commands.filter(
    (row) =>
      ids.has(
        row.id as (typeof DELEGATE_TOOL_IDS)[keyof typeof DELEGATE_TOOL_IDS],
      ) &&
      allowlist.includes(row.id) &&
      row.status !== "stub" &&
      row.enabled !== false,
  );
}

/** Run external codex/claude delegate tools against the open worktree execution. */
export function DelegateExecuteBar({
  sessionId,
  execution,
  actionWhat,
  actionWhere,
  actionVerify,
  runnerEnabled,
  allowlist,
  disabled,
  busy,
  onUpdated,
}: Props) {
  const [commands, setCommands] = useState<SlashCommandRecord[]>([]);
  const [runningId, setRunningId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [pending, setPending] = useState<PendingDelegate | null>(null);

  useEffect(() => {
    if (!runnerEnabled) {
      setCommands([]);
      return;
    }
    let cancelled = false;
    void fetchCommands(sessionId).then((res) => {
      if (!cancelled) setCommands(res.commands ?? []);
    });
    return () => {
      cancelled = true;
    };
  }, [runnerEnabled, sessionId]);

  const runDelegate = useCallback(
    async (toolId: string, prompt: string) => {
      setError(null);
      setStatusMessage(null);
      setRunningId(toolId);
      try {
        const res = await runSessionCommand(sessionId, {
          command_id: toolId,
          args: prompt,
          confirm: true,
        });
        if (!res.ok) {
          const detail =
            (res.result as { detail?: string } | undefined)?.detail ??
            res.detail ??
            "외부 실행에 실패했습니다.";
          setError(String(detail));
          return;
        }
        setStatusMessage("외부 실행이 완료되었습니다. handoff를 확인하세요.");
        onUpdated();
      } catch (exc) {
        setError(exc instanceof Error ? exc.message : String(exc));
      } finally {
        setRunningId(null);
      }
    },
    [onUpdated, sessionId],
  );

  const openConfirm = useCallback(
    (tool: SlashCommandRecord) => {
      setError(null);
      setPending({
        toolId: tool.id,
        toolLabel: tool.label,
        prompt: buildDelegatePrompt({
          what: actionWhat,
          where: actionWhere,
          verify: actionVerify,
        }),
      });
    },
    [actionVerify, actionWhat, actionWhere],
  );

  if (
    !runnerEnabled ||
    execution.status !== "pending_approval" ||
    !isWorktreeExecution(execution) ||
    execution.external_handoff?.evidence_summary
  ) {
    return null;
  }

  const tools = runnableDelegateTools(commands, allowlist);
  const worktreePath = execution.worktree_path?.trim();

  return (
    <>
      <div
        className="delegate-exec-bar"
        role="region"
        aria-label="외부 에이전트 실행"
        data-testid="delegate-exec-bar"
      >
        <div className="delegate-exec-bar__head">
          <WorkPlanIcon name="bolt" size={14} />
          <span>외부 에이전트로 실행</span>
        </div>
        {tools.length === 0 ? (
          <p className="delegate-exec-bar__hint">{DELEGATE_ALLOWLIST_HINT}</p>
        ) : (
          <div className="delegate-exec-bar__actions">
            {tools.map((tool) => (
              <button
                key={tool.id}
                type="button"
                className="plan-btn plan-btn--primary"
                disabled={disabled || busy || runningId != null}
                aria-busy={runningId === tool.id}
                onClick={() => openConfirm(tool)}
              >
                {runningId === tool.id
                  ? "실행 중…"
                  : delegateActionLabel(tool.label)}
              </button>
            ))}
          </div>
        )}
        {statusMessage ? (
          <p
            className="delegate-exec-bar__status"
            role="status"
            aria-live="polite"
          >
            {statusMessage}
          </p>
        ) : null}
        {error ? (
          <p className="delegate-exec-bar__error" role="alert">
            {error}
          </p>
        ) : null}
      </div>

      <MacAlert
        open={pending !== null}
        title="외부 에이전트 실행"
        message={
          pending
            ? `${pending.toolLabel} — worktree에서 로컬 CLI를 실행합니다. 변경 내용은 merge 전에 검토합니다.`
            : undefined
        }
        buttons={[
          {
            label: "취소",
            variant: "cancel",
            onClick: () => setPending(null),
          },
          {
            label: "실행",
            variant: "primary",
            onClick: () => {
              if (!pending) return;
              const { toolId, prompt } = pending;
              setPending(null);
              void runDelegate(toolId, prompt);
            },
          },
        ]}
        onClose={() => setPending(null)}
      >
        {pending ? (
          <div className="delegate-exec-confirm">
            {worktreePath ? (
              <p className="delegate-exec-confirm__meta">
                <span className="delegate-exec-confirm__label">worktree</span>
                <code>{worktreePath}</code>
              </p>
            ) : null}
            <label
              className="delegate-exec-confirm__label"
              htmlFor="delegate-prompt-preview"
            >
              전송 프롬프트
            </label>
            <textarea
              id="delegate-prompt-preview"
              className="delegate-exec-confirm__prompt"
              readOnly
              rows={8}
              value={pending.prompt}
            />
          </div>
        ) : null}
      </MacAlert>
    </>
  );
}
