import { useMemo } from "react";
import { workspacePaletteActions } from "../utils/commandPaletteActions";
import { focusComposerInput } from "../utils/taskBarCopy";
import type { SlashCommandRecord } from "../api/client";
import type { WorkspaceTab } from "../utils/workspaceTabs";

export type RoomPaletteActionsOptions = {
  slashCommands: SlashCommandRecord[];
  setWorkspaceTab: (tab: WorkspaceTab) => void;
  running: boolean;
  handleStop: () => void;
  handleReleaseRunLock: () => void | Promise<void>;
  onOpenSettings?: () => void;
  openTranscriptTab: () => void;
  setText: (text: string) => void;
};

/** Command palette actions for Room workspace — extracted from RoomChat (F9). */
export function useRoomPaletteActions({
  slashCommands,
  setWorkspaceTab,
  running,
  handleStop,
  handleReleaseRunLock,
  onOpenSettings,
  openTranscriptTab,
  setText,
}: RoomPaletteActionsOptions) {
  return useMemo(() => {
    const commandActions = slashCommands
      .filter((cmd) => cmd.enabled !== false)
      .map((cmd) => ({
        id: `slash-${cmd.id}`,
        label: `Insert ${cmd.slash}`,
        hint: `${cmd.agent ?? cmd.kind}${
          cmd.description ? ` · ${cmd.description}` : ""
        }`,
        run: () => {
          openTranscriptTab();
          setText(`${cmd.slash} `);
          window.setTimeout(() => focusComposerInput(), 0);
        },
      }));
    return workspacePaletteActions(setWorkspaceTab, [
      {
        id: "stop-run",
        label: running ? "Stop run" : "Stop run",
        hint: running ? "⌘." : undefined,
        run: () => {
          if (running) handleStop();
        },
      },
      {
        id: "release-lock",
        label: "Release run lock",
        run: () => void handleReleaseRunLock(),
      },
      {
        id: "open-plugins",
        label: "Open settings",
        hint: "Agents · Workspace · Commands",
        run: () => {
          onOpenSettings?.();
        },
      },
      {
        id: "focus-composer",
        label: "Focus composer",
        run: () => focusComposerInput(),
      },
      ...commandActions,
    ]);
  }, [
    setWorkspaceTab,
    running,
    handleStop,
    handleReleaseRunLock,
    onOpenSettings,
    slashCommands,
    openTranscriptTab,
    setText,
  ]);
}
