import type { WorkspaceTab } from "./workspaceTabs";
import { WORKSPACE_TABS } from "./workspaceTabs";

export type CommandAction = {
  id: string;
  label: string;
  hint?: string;
  icon?: string;
  danger?: boolean;
  run: () => void;
};

/** Build actions for the workspace command palette. */
export function workspacePaletteActions(
  onTab: (tab: WorkspaceTab) => void,
  extras: CommandAction[] = [],
): CommandAction[] {
  return [
    ...WORKSPACE_TABS.map((tab) => ({
      id: `tab-${tab.id}`,
      label: `Open ${tab.label}`,
      hint: tab.shortcut,
      run: () => onTab(tab.id),
    })),
    ...extras,
  ];
}
