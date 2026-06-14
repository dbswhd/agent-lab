import { useEffect, useState } from "react";
import {
  buildPermissionsFromForm,
  FULL_AGENT_PERMISSIONS,
  loadDefaultPermissions,
  saveDefaultPermissions,
  type AgentPermissions,
} from "../utils/agentPermissions";
import { MacAlert } from "./MacAlert";

type Props = {
  open: boolean;
  selectedAgents: string[];
  onConfirm: (permissions: AgentPermissions, remember: boolean) => void;
  onCancel: () => void;
};

/** AgentPermissionAlert — per-agent tool permission dialog.
 *
 *  Rendered inside <MacAlert> with .perm-form / .perm-group / .perm-check
 *  classes (overlays.css).
 *  Drop-in for old component that used .mac-checkbox / .mac-alert (macos26).
 */
export function AgentPermissionAlert({
  open,
  selectedAgents,
  onConfirm,
  onCancel,
}: Props) {
  const [cursorTools, setCursorTools] = useState(true);
  const [cursorAgentLab, setCursorAgentLab] = useState(true);
  const [cursorPipeline, setCursorPipeline] = useState(true);
  const [cursorLectureScript, setCursorLectureScript] = useState(true);
  const [codexCli, setCodexCli] = useState(true);
  const [claudeTools, setClaudeTools] = useState(true);
  const [claudeWrite, setClaudeWrite] = useState(true);
  const [claudeAgentLab, setClaudeAgentLab] = useState(true);
  const [claudePipeline, setClaudePipeline] = useState(true);
  const [claudeLectureScript, setClaudeLectureScript] = useState(true);
  const [remember, setRemember] = useState(true);

  /* Restore defaults whenever the dialog opens */
  useEffect(() => {
    if (!open) return;
    const d = loadDefaultPermissions();
    setCursorTools(Boolean(d.cursor?.tools ?? true));
    setCursorAgentLab(Boolean(d.cursor?.local_agent_lab ?? true));
    setCursorPipeline(Boolean(d.cursor?.local_pipeline ?? true));
    setCursorLectureScript(Boolean(d.cursor?.local_lecture_script ?? true));
    setCodexCli(Boolean(d.codex?.cli ?? true));
    setClaudeTools(
      Boolean(d.claude?.tools ?? FULL_AGENT_PERMISSIONS.claude.tools),
    );
    setClaudeWrite(
      Boolean(d.claude?.write ?? FULL_AGENT_PERMISSIONS.claude.write),
    );
    setClaudeAgentLab(
      Boolean(
        d.claude?.local_agent_lab ??
        FULL_AGENT_PERMISSIONS.claude.local_agent_lab,
      ),
    );
    setClaudePipeline(
      Boolean(
        d.claude?.local_pipeline ??
        FULL_AGENT_PERMISSIONS.claude.local_pipeline,
      ),
    );
    setClaudeLectureScript(
      Boolean(
        d.claude?.local_lecture_script ??
        FULL_AGENT_PERMISSIONS.claude.local_lecture_script,
      ),
    );
  }, [open]);

  const showCursor = selectedAgents.includes("cursor");
  const showCodex = selectedAgents.includes("codex");
  const showClaude = selectedAgents.includes("claude");

  function handleConfirm() {
    const perms = buildPermissionsFromForm(selectedAgents, {
      cursorTools,
      cursorAgentLab,
      cursorPipeline,
      cursorLectureScript,
      codexCli,
      claudeTools,
      claudeWrite,
      claudeAgentLab,
      claudePipeline,
      claudeLectureScript,
    });
    if (remember) saveDefaultPermissions(perms);
    onConfirm(perms, remember);
  }

  return (
    <MacAlert
      open={open}
      title="에이전트 권한"
      message="이번 메시지에 대해 각 에이전트가 사용할 수 있는 기능을 선택하세요."
      onClose={onCancel}
      buttons={[
        { label: "취소", variant: "cancel", onClick: onCancel },
        { label: "허용하고 전송", variant: "primary", onClick: handleConfirm },
      ]}
    >
      <div className="perm-form">
        {showCursor && (
          <fieldset className="perm-group">
            <legend>Cursor</legend>
            <label className="perm-check">
              <input
                type="checkbox"
                className="checkbox"
                checked={cursorTools}
                onChange={(e) => setCursorTools(e.target.checked)}
              />
              도구 사용 (파일 읽기·검색)
            </label>
            <label className="perm-check">
              <input
                type="checkbox"
                className="checkbox"
                checked={cursorAgentLab}
                onChange={(e) => setCursorAgentLab(e.target.checked)}
              />
              agent-lab 프로젝트 접근
            </label>
            <label className="perm-check">
              <input
                type="checkbox"
                className="checkbox"
                checked={cursorPipeline}
                onChange={(e) => setCursorPipeline(e.target.checked)}
              />
              quant-pipeline 접근
            </label>
            <label className="perm-check">
              <input
                type="checkbox"
                className="checkbox"
                checked={cursorLectureScript}
                onChange={(e) => setCursorLectureScript(e.target.checked)}
              />
              lecture-script 접근
            </label>
          </fieldset>
        )}

        {showCodex && (
          <fieldset className="perm-group">
            <legend>Codex</legend>
            <label className="perm-check">
              <input
                type="checkbox"
                className="checkbox"
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
                type="checkbox"
                className="checkbox"
                checked={claudeTools}
                onChange={(e) => setClaudeTools(e.target.checked)}
              />
              도구 사용 (Claude Code — 읽기·검색)
            </label>
            <label className="perm-check">
              <input
                type="checkbox"
                className="checkbox"
                checked={claudeWrite}
                onChange={(e) => setClaudeWrite(e.target.checked)}
              />
              파일 편집 (Claude Code acceptEdits)
            </label>
            <label className="perm-check">
              <input
                type="checkbox"
                className="checkbox"
                checked={claudeAgentLab}
                onChange={(e) => setClaudeAgentLab(e.target.checked)}
              />
              agent-lab 프로젝트 접근
            </label>
            <label className="perm-check">
              <input
                type="checkbox"
                className="checkbox"
                checked={claudePipeline}
                onChange={(e) => setClaudePipeline(e.target.checked)}
              />
              quant-pipeline 접근
            </label>
            <label className="perm-check">
              <input
                type="checkbox"
                className="checkbox"
                checked={claudeLectureScript}
                onChange={(e) => setClaudeLectureScript(e.target.checked)}
              />
              lecture-script 접근
            </label>
          </fieldset>
        )}

        <label className="perm-check perm-remember">
          <input
            type="checkbox"
            className="checkbox"
            checked={remember}
            onChange={(e) => setRemember(e.target.checked)}
          />
          다음에도 이 설정 기억
        </label>
      </div>
    </MacAlert>
  );
}
