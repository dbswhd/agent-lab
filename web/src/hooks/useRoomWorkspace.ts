import { useCallback, useEffect, useState } from "react";
import { fetchSessionSetupOptions } from "../api/client";
import type { WorkspacePreset } from "../utils/sessionSetup";
import {
  CUSTOM_WORKSPACE_ID,
  getStoredWorkspaceId,
  getStoredWorkspacePath,
  setStoredWorkspaceId,
  setStoredWorkspacePath,
} from "../utils/sessionSetup";

export function useRoomWorkspace(sessionId: string | null) {
  const [workspaceId, setWorkspaceIdState] = useState(getStoredWorkspaceId);
  const [workspacePath, setWorkspacePathState] = useState<string | null>(
    getStoredWorkspacePath,
  );
  const [, setSetupWorkspaces] = useState<WorkspacePreset[]>([]);

  const setWorkspaceId = useCallback((id: string, path?: string | null) => {
    setWorkspaceIdState(id);
    setStoredWorkspaceId(id);
    if (path !== undefined) {
      setWorkspacePathState(path);
      setStoredWorkspacePath(path);
    }
  }, []);

  useEffect(() => {
    fetchSessionSetupOptions()
      .then((opts) => {
        setSetupWorkspaces(opts.workspaces);
        const wsIds = new Set(opts.workspaces.map((w) => w.id));
        if (workspaceId !== CUSTOM_WORKSPACE_ID && !wsIds.has(workspaceId)) {
          setWorkspaceId(opts.defaults.workspace_id, null);
        }
      })
      .catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps -- hydrate once; stored ids validated against API
  }, []);

  useEffect(() => {
    if (sessionId !== null) return;
    setWorkspaceIdState(getStoredWorkspaceId());
    setWorkspacePathState(getStoredWorkspacePath());
  }, [sessionId]);

  return {
    workspaceId,
    workspacePath,
    setWorkspaceId,
  };
}
