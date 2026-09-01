import { useCallback, useEffect, useState } from "react";
import {
  fetchCommands,
  runSessionCommand,
  type PlanExecutionRecord,
  type SlashCommandRecord,
} from "../api/client";
import {
  buildDelegatePrompt,
  DELEGATE_TOOL_IDS,
} from "../utils/externalHandoff";
import { isWorktreeExecution } from "../utils/planExecuteWorktree";
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
    async (toolId: string) => {
      setError(null);
      setRunningId(toolId);
      try {
        const args = buildDelegatePrompt({
          what: actionWhat,
          where: actionWhere,
          verify: actionVerify,
        });
        const res = await runSessionCommand(sessionId, {
          command_id: toolId,
          args,
          confirm: true,
        });
        if (!res.ok) {
          const detail =
            (res.result as { detail?: string } | undefined)?.detail ??
            res.detail ??
            "delegate command failed";
          setError(String(detail));
          return;
        }
        onUpdated();
      } catch (exc) {
        setError(exc instanceof Error ? exc.message : String(exc));
      } finally {
        setRunningId(null);
      }
    },
    [actionVerify, actionWhat, actionWhere, onUpdated, sessionId],
  );

  if (
    execution.status !== "pending_approval" ||
    !isWorktreeExecution(execution)
  ) {
    return null;
  }

  const tools = runnableDelegateTools(commands, allowlist);
  const hasHandoff = Boolean(execution.external_handoff?.evidence_summary);

  return (
    <div
      className="delegate-exec-bar"
      role="region"
      aria-label="외부 delegate 실행"
      data-testid="delegate-exec-bar"
    >
      <div className="delegate-exec-bar__head">
        <WorkPlanIcon name="bolt" size={14} />
        <span>외부 CLI delegate</span>
        {hasHandoff ? (
          <span className="badge badge--ok">handoff attached</span>
        ) : null}
      </div>
      {!runnerEnabled ? (
        <p className="delegate-exec-bar__hint">
          서버에 <code>AGENT_LAB_EXTERNAL_TOOLS=1</code> 설정 후{" "}
          <code>~/.agent-lab/tools.yaml</code>을 등록하세요.
        </p>
      ) : tools.length === 0 ? (
        <p className="delegate-exec-bar__hint">
          Tools → Plugins → External에서 <code>codex-delegate</code> 또는{" "}
          <code>claude-delegate</code>를 세션 allowlist에 추가하세요.
        </p>
      ) : (
        <div className="delegate-exec-bar__actions">
          {tools.map((tool) => (
            <button
              key={tool.id}
              type="button"
              className="plan-btn plan-btn--primary"
              disabled={disabled || busy || runningId != null}
              onClick={() => void runDelegate(tool.id)}
            >
              {runningId === tool.id ? "실행 중…" : tool.label}
            </button>
          ))}
        </div>
      )}
      {error ? (
        <p className="delegate-exec-bar__error" role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}
