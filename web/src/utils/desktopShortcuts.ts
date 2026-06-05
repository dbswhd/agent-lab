import type { WorkspaceTab } from "./workspaceTabs";
import { normalizeWorkspaceTab } from "./workspaceTabs";

/** @deprecated Use WorkspaceTab */
export type ContentTab = "chat" | "plan";

export const CONTENT_TAB_SHORTCUT_EVENT = "agent-lab:content-tab-shortcut";
export const WORKSPACE_TAB_SHORTCUT_EVENT = "agent-lab:workspace-tab-shortcut";
export const COMMAND_PALETTE_EVENT = "agent-lab:command-palette";

const LEGACY_TO_WORKSPACE: Record<ContentTab, WorkspaceTab> = {
  chat: "transcript",
  plan: "work",
};

const SHORTCUT_INDEX: Record<string, WorkspaceTab> = {
  "1": "transcript",
  "2": "work",
  "3": "run",
  "4": "artifacts",
};

export function requestWorkspaceTab(tab: WorkspaceTab): void {
  window.dispatchEvent(
    new CustomEvent<WorkspaceTab>(WORKSPACE_TAB_SHORTCUT_EVENT, { detail: tab }),
  );
}

/** @deprecated Use requestWorkspaceTab */
export function requestContentTab(tab: ContentTab): void {
  requestWorkspaceTab(LEGACY_TO_WORKSPACE[tab]);
}

export function requestWorkspaceTabByIndex(index: string): void {
  const tab = SHORTCUT_INDEX[index];
  if (tab) requestWorkspaceTab(tab);
}

export function openCommandPalette(): void {
  window.dispatchEvent(new CustomEvent(COMMAND_PALETTE_EVENT));
}

export { normalizeWorkspaceTab };
