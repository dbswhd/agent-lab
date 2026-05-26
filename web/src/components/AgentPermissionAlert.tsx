import { useEffect, useState } from "react";
import type { AgentPermissions } from "../utils/agentPermissions";
import {
  buildPermissionsFromForm,
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
  const [remember, setRemember] = useState(true);

  useEffect(() => {
    if (!open) return;
    const d = loadDefaultPermissions();
    setCursorTools(Boolean(d.cursor?.tools));
    setCursorAgentLab(Boolean(d.cursor?.local_agent_lab));
    setCursorPipeline(Boolean(d.cursor?.local_pipeline));
    setCodexCli(Boolean(d.codex?.cli));
  }, [open]);

  const showCursor = selectedAgents.includes("cursor");
  const showCodex = selectedAgents.includes("codex");

  function handleOk() {
    const p = buildPermissionsFromForm(selectedAgents, {
      cursorTools,
      cursorAgentLab,
      cursorPipeline,
      codexCli,
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
                type="checkbox"
                checked={cursorTools}
                onChange={(e) => setCursorTools(e.target.checked)}
              />
              도구 사용 (파일 읽기·검색)
            </label>
            <label className="perm-check">
              <input
                type="checkbox"
                checked={cursorAgentLab}
                onChange={(e) => setCursorAgentLab(e.target.checked)}
              />
              agent-lab 프로젝트 접근
            </label>
            <label className="perm-check">
              <input
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
                type="checkbox"
                checked={codexCli}
                onChange={(e) => setCodexCli(e.target.checked)}
              />
              Codex CLI 실행 허용
            </label>
          </fieldset>
        )}
        {selectedAgents.includes("claude") && (
          <p className="perm-hint">Claude는 API 대화만 사용합니다 (추가 권한 없음).</p>
        )}
        <label className="perm-check perm-remember">
          <input
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
