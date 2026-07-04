import {
  useCallback,
  useEffect,
  useState,
  type Dispatch,
  type MutableRefObject,
  type SetStateAction,
} from "react";
import {
  fetchCommands,
  type AuthRunRef,
  type SlashCommandRecord,
} from "../api/client";
import type {
  ModelPopoverAgent,
  ModelPopoverSidePanel,
} from "../components/ComposerModelPopover";

export type SlashCommandChoicesState = {
  command: SlashCommandRecord;
  argsPrefix: string;
  prompt: string;
  kind?: string;
  options: { value: string; label: string; ready?: boolean }[];
};

export type SlashCommandMultiChoicesState = {
  command: SlashCommandRecord;
  argsPrefix: string;
  prompt: string;
  current: string[];
  options: { value: string; label: string }[];
};

export type SlashCommandScopeChoicesState = {
  command: SlashCommandRecord;
  composition: string[];
  prompt: string;
  options: { value: string; label: string }[];
};

export type SlashCommandModelPopoverState = {
  command: SlashCommandRecord;
  autoEnabled: boolean;
  agents: ModelPopoverAgent[];
  sidePanel: ModelPopoverSidePanel | null;
};

export type SlashCommandSecretState = {
  command: SlashCommandRecord;
  argsPrefix: string;
  prompt: string;
};

export type UseRoomSlashCommandsArgs = {
  sessionId: string | null;
  activeSessionIdRef: MutableRefObject<string | null>;
};

/** Phase 1c (F6): slash command catalog + overlay UI state — extracted from RoomChat. */
export function useRoomSlashCommands({
  sessionId,
  activeSessionIdRef,
}: UseRoomSlashCommandsArgs) {
  const [slashCommands, setSlashCommands] = useState<SlashCommandRecord[]>([]);
  const [commandHint, setCommandHint] = useState<string | null>(null);
  const [authRun, setAuthRun] = useState<AuthRunRef | null>(null);
  const [secretCommand, setSecretCommand] =
    useState<SlashCommandSecretState | null>(null);
  const [secretValue, setSecretValue] = useState("");
  const [commandChoices, setCommandChoices] =
    useState<SlashCommandChoicesState | null>(null);
  const [commandChoiceIndex, setCommandChoiceIndex] = useState(0);
  const [commandMultiChoices, setCommandMultiChoices] =
    useState<SlashCommandMultiChoicesState | null>(null);
  const [commandScopeChoices, setCommandScopeChoices] =
    useState<SlashCommandScopeChoicesState | null>(null);
  const [multiSelected, setMultiSelected] = useState<Set<string>>(new Set());
  const [modelPopover, setModelPopover] =
    useState<SlashCommandModelPopoverState | null>(null);
  const [externalCommandConfirm, setExternalCommandConfirm] = useState<{
    command: SlashCommandRecord;
    args: string;
  } | null>(null);

  const dismissSlashOverlays = useCallback(() => {
    setCommandChoices(null);
    setCommandMultiChoices(null);
    setCommandScopeChoices(null);
    setModelPopover(null);
    setSecretCommand(null);
    setSecretValue("");
    setAuthRun(null);
  }, []);

  useEffect(() => {
    if (
      !commandChoices &&
      !commandMultiChoices &&
      !commandScopeChoices &&
      !modelPopover &&
      !authRun &&
      !secretCommand
    ) {
      return;
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") dismissSlashOverlays();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [
    authRun,
    commandChoices,
    commandMultiChoices,
    commandScopeChoices,
    dismissSlashOverlays,
    modelPopover,
    secretCommand,
  ]);

  const refreshCommands = useCallback(
    (overrideId?: string | null) => {
      const sid = overrideId ?? sessionId ?? activeSessionIdRef.current;
      void fetchCommands(sid)
        .then((res) => {
          setSlashCommands(res.commands ?? []);
          if (res.discovery_refreshing) {
            window.setTimeout(() => {
              void fetchCommands(sid)
                .then((refreshed) => setSlashCommands(refreshed.commands ?? []))
                .catch(() => undefined);
            }, 300);
          }
        })
        .catch(() => setSlashCommands([]));
    },
    [activeSessionIdRef, sessionId],
  );

  useEffect(() => {
    refreshCommands();
  }, [refreshCommands]);

  return {
    slashCommands,
    setSlashCommands,
    commandHint,
    setCommandHint,
    authRun,
    setAuthRun,
    secretCommand,
    setSecretCommand,
    secretValue,
    setSecretValue,
    commandChoices,
    setCommandChoices,
    commandChoiceIndex,
    setCommandChoiceIndex,
    commandMultiChoices,
    setCommandMultiChoices,
    commandScopeChoices,
    setCommandScopeChoices,
    multiSelected,
    setMultiSelected,
    modelPopover,
    setModelPopover,
    externalCommandConfirm,
    setExternalCommandConfirm,
    dismissSlashOverlays,
    refreshCommands,
  };
}

export function useSlashCommandChoiceKeyboard(
  commandChoices: SlashCommandChoicesState | null,
  commandChoiceIndex: number,
  setCommandChoiceIndex: Dispatch<SetStateAction<number>>,
  executeSlashCommand: (
    command: SlashCommandRecord,
    args: string,
  ) => Promise<void>,
) {
  useEffect(() => {
    if (!commandChoices) return;
    const onChoiceKey = (event: KeyboardEvent) => {
      const count = commandChoices.options.length;
      if (event.key === "ArrowDown") {
        event.preventDefault();
        setCommandChoiceIndex((index) => (index + 1) % count);
      } else if (event.key === "ArrowUp") {
        event.preventDefault();
        setCommandChoiceIndex((index) => (index - 1 + count) % count);
      } else if (event.key === "PageDown") {
        event.preventDefault();
        setCommandChoiceIndex((index) => Math.min(index + 10, count - 1));
      } else if (event.key === "PageUp") {
        event.preventDefault();
        setCommandChoiceIndex((index) => Math.max(index - 10, 0));
      } else if (event.key === "Enter") {
        event.preventDefault();
        const option = commandChoices.options[commandChoiceIndex];
        if (option) {
          void executeSlashCommand(
            commandChoices.command,
            `${commandChoices.argsPrefix} ${option.value}`.trim(),
          );
        }
      }
    };
    document.addEventListener("keydown", onChoiceKey);
    return () => document.removeEventListener("keydown", onChoiceKey);
  }, [
    commandChoiceIndex,
    commandChoices,
    executeSlashCommand,
    setCommandChoiceIndex,
  ]);
}
