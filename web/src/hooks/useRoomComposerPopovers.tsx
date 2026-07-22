import {
  useMemo,
  type Dispatch,
  type ReactNode,
  type SetStateAction,
} from "react";
import {
  runRoomSlash,
  type AuthRunRef,
  type SlashCommandRecord,
} from "../api/client";
import { ComposerAuthFlowPopover } from "../components/ComposerAuthFlowPopover";
import { ComposerAuthPickerPopover } from "../components/ComposerAuthPickerPopover";
import { ComposerAuthSecretPopover } from "../components/ComposerAuthSecretPopover";
import { ComposerChoicePopover } from "../components/ComposerChoicePopover";
import { ComposerModelPopover } from "../components/ComposerModelPopover";
import { sortAgentIds } from "../utils/agentOrder";
import { focusComposerInput } from "../utils/taskBarCopy";
import type {
  SlashCommandChoicesState,
  SlashCommandModelPopoverState,
  SlashCommandMultiChoicesState,
  SlashCommandScopeChoicesState,
  SlashCommandSecretState,
} from "./useRoomSlashCommands";

export type RoomComposerPopoversOptions = {
  sessionId: string | null;
  authRun: AuthRunRef | null;
  setAuthRun: Dispatch<SetStateAction<AuthRunRef | null>>;
  secretCommand: SlashCommandSecretState | null;
  secretValue: string;
  setSecretValue: Dispatch<SetStateAction<string>>;
  setSecretCommand: Dispatch<SetStateAction<SlashCommandSecretState | null>>;
  commandChoices: SlashCommandChoicesState | null;
  commandChoiceIndex: number;
  setCommandChoiceIndex: Dispatch<SetStateAction<number>>;
  commandScopeChoices: SlashCommandScopeChoicesState | null;
  setCommandScopeChoices: Dispatch<
    SetStateAction<SlashCommandScopeChoicesState | null>
  >;
  commandMultiChoices: SlashCommandMultiChoicesState | null;
  setCommandMultiChoices: Dispatch<
    SetStateAction<SlashCommandMultiChoicesState | null>
  >;
  multiSelected: Set<string>;
  setMultiSelected: Dispatch<SetStateAction<Set<string>>>;
  modelPopover: SlashCommandModelPopoverState | null;
  setModelPopover: Dispatch<
    SetStateAction<SlashCommandModelPopoverState | null>
  >;
  setCommandChoices: Dispatch<SetStateAction<SlashCommandChoicesState | null>>;
  setCommandHint: Dispatch<SetStateAction<string | null>>;
  executeSlashCommand: (
    command: SlashCommandRecord,
    args: string,
    skipConfirm?: boolean,
  ) => Promise<void>;
  handleAuthRunComplete: () => Promise<void>;
  applySessionScopedModels: (composition: string[]) => void;
};

export type RoomComposerPopovers = {
  modelPopoverNode: ReactNode;
  authPopover: ReactNode;
  authPickerPopover: ReactNode;
  choicePopover: ReactNode;
};

/** Slash-command overlay popovers — extracted from RoomChat (F9). */
export function useRoomComposerPopovers(
  options: RoomComposerPopoversOptions,
): RoomComposerPopovers {
  const {
    sessionId,
    authRun,
    setAuthRun,
    secretCommand,
    secretValue,
    setSecretValue,
    setSecretCommand,
    commandChoices,
    commandChoiceIndex,
    setCommandChoiceIndex,
    commandScopeChoices,
    setCommandScopeChoices,
    commandMultiChoices,
    setCommandMultiChoices,
    multiSelected,
    setMultiSelected,
    modelPopover,
    setModelPopover,
    setCommandChoices,
    setCommandHint,
    executeSlashCommand,
    handleAuthRunComplete,
    applySessionScopedModels,
  } = options;

  const modelPopoverNode = useMemo(() => {
    if (!modelPopover) return null;
    return (
      <ComposerModelPopover
        command={modelPopover.command}
        autoEnabled={modelPopover.autoEnabled}
        agents={modelPopover.agents}
        sidePanel={modelPopover.sidePanel}
        selectedAgents={multiSelected}
        onProviderDrill={(providerId) => {
          void executeSlashCommand(modelPopover.command, providerId);
        }}
        onSidePresetSelect={(providerId, value) => {
          void executeSlashCommand(
            modelPopover.command,
            `${providerId} ${value}`.trim(),
          );
        }}
        onSideEffortSelect={(providerId, effort) => {
          void executeSlashCommand(
            modelPopover.command,
            `${providerId} effort ${effort}`.trim(),
          );
        }}
        onSideClose={() =>
          setModelPopover((prev) =>
            prev ? { ...prev, sidePanel: null } : prev,
          )
        }
        onAgentToggle={(value) => {
          setMultiSelected((prev) => {
            const next = new Set(prev);
            if (next.has(value)) next.delete(value);
            else next.add(value);
            return next;
          });
        }}
        onAgentsApply={() => {
          const selected = sortAgentIds(
            modelPopover.agents
              .filter((opt) => multiSelected.has(opt.value))
              .map((opt) => opt.value),
          ).join(",");
          const cmd = modelPopover.command;
          setModelPopover(null);
          setMultiSelected(new Set());
          if (!sessionId) {
            const next = sortAgentIds(selected.split(",").filter(Boolean));
            if (next.length === 0) return;
            setCommandScopeChoices({
              command: cmd,
              composition: next,
              prompt: `[${next.join(", ")}] — 적용 범위를 선택하세요`,
              options: [
                {
                  value: "session",
                  label: "이번 세션만 (세션 동안 유지)",
                },
                {
                  value: "default",
                  label: "기본값으로 저장",
                },
              ],
            });
            return;
          }
          // Default to session scope for the picker's quick-toggle flow —
          // asking "session vs default?" on every mid-conversation roster
          // tweak (e.g. dropping an agent whose auth just expired) turned a
          // 2-click change into 4. Power users who want to persist the
          // default can still type `/model compose <ids> default` directly.
          void executeSlashCommand(cmd, `compose ${selected} session`.trim());
        }}
        onCancel={() => setModelPopover(null)}
      />
    );
  }, [
    executeSlashCommand,
    modelPopover,
    multiSelected,
    sessionId,
    setCommandScopeChoices,
    setModelPopover,
    setMultiSelected,
  ]);

  const authPopover = useMemo(() => {
    if (authRun) {
      return (
        <ComposerAuthFlowPopover
          run={authRun}
          onComplete={handleAuthRunComplete}
          onClose={() => {
            setAuthRun(null);
            focusComposerInput();
          }}
        />
      );
    }
    if (secretCommand) {
      return (
        <ComposerAuthSecretPopover
          prompt={secretCommand.prompt}
          value={secretValue}
          onChange={setSecretValue}
          onSubmit={() => {
            if (!secretValue.trim()) return;
            const args = `${secretCommand.argsPrefix} ${secretValue}`.trim();
            const cmd = secretCommand.command;
            setSecretCommand(null);
            setSecretValue("");
            void executeSlashCommand(cmd, args);
          }}
          onCancel={() => {
            setSecretCommand(null);
            setSecretValue("");
            focusComposerInput();
          }}
        />
      );
    }
    return null;
  }, [
    authRun,
    executeSlashCommand,
    handleAuthRunComplete,
    secretCommand,
    secretValue,
    setAuthRun,
    setSecretCommand,
    setSecretValue,
  ]);

  const authPickerPopover = useMemo(() => {
    if (!commandChoices) return null;
    const cmd = commandChoices.command;
    if (cmd.id !== "login" && cmd.id !== "logout") return null;
    const variant =
      commandChoices.kind === "auth_method" ? "methods" : "agents";
    return (
      <ComposerAuthPickerPopover
        action={cmd.id}
        title={commandChoices.prompt}
        variant={variant}
        options={commandChoices.options}
        highlightedIndex={commandChoiceIndex}
        onHighlight={setCommandChoiceIndex}
        onSelect={(value) =>
          void executeSlashCommand(
            commandChoices.command,
            `${commandChoices.argsPrefix} ${value}`.trim(),
          )
        }
        onCancel={() => setCommandChoices(null)}
      />
    );
  }, [
    commandChoiceIndex,
    commandChoices,
    executeSlashCommand,
    setCommandChoiceIndex,
    setCommandChoices,
  ]);

  const choicePopover = useMemo(() => {
    if (commandChoices) {
      const cmd = commandChoices.command;
      if (cmd.id === "login" || cmd.id === "logout") {
        return null;
      }
      return (
        <ComposerChoicePopover
          variant="single"
          command={commandChoices.command}
          prompt={commandChoices.prompt}
          options={commandChoices.options}
          highlightedIndex={commandChoiceIndex}
          onHighlight={setCommandChoiceIndex}
          onSelect={(value) =>
            void executeSlashCommand(
              commandChoices.command,
              `${commandChoices.argsPrefix} ${value}`.trim(),
            )
          }
          onCancel={() => setCommandChoices(null)}
        />
      );
    }
    if (commandScopeChoices) {
      return (
        <ComposerChoicePopover
          variant="scope"
          command={commandScopeChoices.command}
          prompt={commandScopeChoices.prompt}
          options={commandScopeChoices.options}
          onSelect={(value) => {
            const cmd = commandScopeChoices.command;
            const comp = commandScopeChoices.composition;
            const composition = comp.join(",");
            setCommandScopeChoices(null);
            if (!sessionId && cmd.id === "model") {
              if (value === "default") {
                void runRoomSlash(`/model compose ${composition} default`).then(
                  () => {
                    setCommandHint(`기본값으로 저장했습니다 (${composition}).`);
                  },
                );
              } else {
                applySessionScopedModels(comp);
              }
            } else {
              void executeSlashCommand(cmd, `${composition} ${value}`.trim());
            }
          }}
          onCancel={() => setCommandScopeChoices(null)}
        />
      );
    }
    if (commandMultiChoices) {
      return (
        <ComposerChoicePopover
          variant="multi"
          command={commandMultiChoices.command}
          prompt={commandMultiChoices.prompt}
          options={commandMultiChoices.options}
          selected={multiSelected}
          onToggle={(value) => {
            setMultiSelected((prev) => {
              const next = new Set(prev);
              if (next.has(value)) next.delete(value);
              else next.add(value);
              return next;
            });
          }}
          onApply={() => {
            const selected = sortAgentIds(
              commandMultiChoices.options
                .filter((opt) => multiSelected.has(opt.value))
                .map((opt) => opt.value),
            ).join(",");
            const cmd = commandMultiChoices.command;
            setCommandMultiChoices(null);
            setMultiSelected(new Set());
            if (!sessionId && cmd.id === "model") {
              const comp = selected.split(",").filter(Boolean);
              setCommandScopeChoices({
                command: cmd,
                composition: comp,
                prompt: `[${comp.join(", ")}] — 적용 범위를 선택하세요`,
                options: [
                  {
                    value: "session",
                    label: "이번 세션만 (세션 동안 유지)",
                  },
                  {
                    value: "default",
                    label: "기본값으로 저장",
                  },
                ],
              });
            } else {
              void executeSlashCommand(cmd, selected);
            }
          }}
          onCancel={() => {
            setCommandMultiChoices(null);
            setMultiSelected(new Set());
          }}
        />
      );
    }
    return null;
  }, [
    applySessionScopedModels,
    commandChoiceIndex,
    commandChoices,
    commandMultiChoices,
    commandScopeChoices,
    executeSlashCommand,
    multiSelected,
    sessionId,
    setCommandChoiceIndex,
    setCommandChoices,
    setCommandHint,
    setCommandMultiChoices,
    setCommandScopeChoices,
    setMultiSelected,
  ]);

  return { modelPopoverNode, authPopover, authPickerPopover, choicePopover };
}
