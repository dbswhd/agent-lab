import { useEffect, useState } from "react";
import type { AgentPermissions } from "../utils/agentPermissions";
import {
  buildPermissionsFromForm,
  FULL_AGENT_PERMISSIONS,
  loadDefaultPermissions,
  saveDefaultPermissions,
} from "../utils/agentPermissions";
import { MacAlert } from "./MacAlert";

type Props = {
  open: boolean;
  selectedAgents: string[];
  onConfirm: (permissions: AgentPermissions, remember: boolean) => void;
  onCancel: () => void;
};

export function AgentPermissionAlert({
  open,
  selectedAgents,
  onConfirm,
  onCancel,
}: Props) {
  const [cursorTools, setCursorTools] = useState(false);
  const [cursorAgentLab, setCursorAgentLab] = useState(false);
  const [cursorPipeline, setCursorPipeline] = useState(false);
  const [codexCli, setCodexCli] = useState(false);
  const [claudeTools, setClaudeTools] = useState(false);
  const [claudeWrite, setClaudeWrite] = useState(false);
  const [claudeAgentLab, setClaudeAgentLab] = useState(false);
  const [claudePipeline, setClaudePipeline] = useState(false);
  const [remember, setRemember] = useState(true);

  useEffect(() => {
    if (!open) return;
    const d = loadDefaultPermissions();
    setCursorTools(Boolean(d.cursor?.tools ?? true));
    setCursorAgentLab(Boolean(d.cursor?.local_agent_lab ?? true));
    setCursorPipeline(Boolean(d.cursor?.local_pipeline ?? true));
    setCodexCli(Boolean(d.codex?.cli ?? true));
    setClaudeTools(Boolean(d.claude?.tools ?? FULL_AGENT_PERMISSIONS.claude.tools));
    setClaudeWrite(Boolean(d.claude?.write ?? FULL_AGENT_PERMISSIONS.claude.write));
    setClaudeAgentLab(
      Boolean(d.claude?.local_agent_lab ?? FULL_AGENT_PERMISSIONS.claude.local_agent_lab),
    );
    setClaudePipeline(
      Boolean(d.claude?.local_pipeline ?? FULL_AGENT_PERMISSIONS.claude.local_pipeline),
    );
  }, [open]);

  const showCursor = selectedAgents.includes("cursor");
  const showCodex = selectedAgents.includes("codex");
  const showClaude = selectedAgents.includes("claude");

  function handleOk() {
    const p = buildPermissionsFromForm(selectedAgents, {
      cursorTools,
      cursorAgentLab,
      cursorPipeline,
      codexCli,
      claudeTools,
      claudeWrite,
      claudeAgentLab,
      claudePipeline,
    });
    if (remember) saveDefaultPermissions(p);
    onConfirm(p, remember);
  }

  return (
    <MacAlert
      open={open}
      title="에이전트 권한"
      message="이번 메시지에 대해 각 에이전트가 사용할 수 있는 기능을 선택하세요."
      onClose={onCancel}
      buttons={[
        { label: "취소", variant: "cancel", onClick: onCancel },
        { label: "허용하고 전송", variant: "default", onClick: handleOk },
      ]}
    >
      <div className="perm-form">
        {showCursor && (
          <fieldset className="perm-group">
            <legend>Cursor</legend>
            <label className="perm-check">
              <input
                className="mac-checkbox"
                type="checkbox"
                checked={cursorTools}
                onChange={(e) => setCursorTools(e.target.checked)}
              />
              도구 사용 (파일 읽기·검색)
            </label>
            <label className="perm-check">
              <input
                className="mac-checkbox"
                type="checkbox"
                checked={cursorAgentLab}
                onChange={(e) => setCursorAgentLab(e.target.checked)}
              />
              agent-lab 프로젝트 접근
            </label>
            <label className="perm-check">
              <input
                className="mac-checkbox"
                type="checkbox"
                checked={cursorPipeline}
                onChange={(e) => setCursorPipeline(e.target.checked)}
              />
              quant-pipeline 접근
            </label>
          </fieldset>
        )}
        {showCodex && (
          <fieldset className="perm-group">
            <legend>Codex</legend>
            <label className="perm-check">
              <input
                className="mac-checkbox"
                type="checkbox"
                checked={codexCli}
                onChange={(e) => setCodexCli(e.target.checked)}
              />
              Codex CLI 실행 허용
            </label>
          </fieldset>
        )}
        {showClaude && (
          <fieldset className="perm-group">
            <legend>Claude</legend>
            <label className="perm-check">
              <input
                className="mac-checkbox"
                type="checkbox"
                checked={claudeTools}
                onChange={(e) => setClaudeTools(e.target.checked)}
              />
              도구 사용 (Claude Code — 읽기·검색)
            </label>
            <label className="perm-check">
              <input
                className="mac-checkbox"
                type="checkbox"
                checked={claudeWrite}
                onChange={(e) => setClaudeWrite(e.target.checked)}
              />
              파일 편집 (Claude Code acceptEdits)
            </label>
            <label className="perm-check">
              <input
                className="mac-checkbox"
                type="checkbox"
                checked={claudeAgentLab}
                onChange={(e) => setClaudeAgentLab(e.target.checked)}
              />
              agent-lab 프로젝트 접근
            </label>
            <label className="perm-check">
              <input
                className="mac-checkbox"
                type="checkbox"
                checked={claudePipeline}
                onChange={(e) => setClaudePipeline(e.target.checked)}
              />
              quant-pipeline 접근
            </label>
          </fieldset>
        )}
        <label className="perm-check perm-remember">
          <input
            className="mac-checkbox"
            type="checkbox"
            checked={remember}
            onChange={(e) => setRemember(e.target.checked)}
          />
          다음에도 이 설정 기억
        </label>
      </div>
    </MacAlert>
  );
}
