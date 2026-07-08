import {
  useCallback,
  useEffect,
  type Dispatch,
  type MutableRefObject,
  type SetStateAction,
} from "react";
import {
  fetchCommands,
  matchSlashCommand,
  reconnectClaudeAuth,
  runGlobalCommand,
  runRoomSlash,
  runSessionCommand,
  SESSIONLESS_ACCOUNT_COMMAND_IDS,
  type AgentOption,
  type AuthRunRef,
  type SlashCommandRecord,
} from "../api/client";
import type {
  ModelPopoverAgent,
  ModelPopoverSidePanel,
} from "../components/ComposerModelPopover";
import {
  appendSessionMessages,
  resolveRunSessionKey,
} from "../run/runSessionRegistry";
import { sortAgentIds, sortAgentPickerOptions } from "../utils/agentOrder";
import {
  parseModelSlashArgs,
  writePendingRoomModels,
} from "../utils/modelSlash";
import { focusComposerInput } from "../utils/taskBarCopy";
import type {
  SlashCommandChoicesState,
  SlashCommandModelPopoverState,
  SlashCommandMultiChoicesState,
  SlashCommandScopeChoicesState,
  SlashCommandSecretState,
} from "./useRoomSlashCommands";

export type ExecuteSlashCommandFn = (
  command: SlashCommandRecord,
  args: string,
  confirm?: boolean,
) => Promise<void>;

export type RunSlashCommandFn = (
  command: SlashCommandRecord,
  rawText?: string,
) => Promise<void>;

export type RoomSlashExecuteOptions = {
  sessionId: string | null;
  activeSessionIdRef: MutableRefObject<string | null>;
  agents: AgentOption[];
  slashCommands: SlashCommandRecord[];
  authRun: AuthRunRef | null;
  commandChoices: SlashCommandChoicesState | null;
  commandChoiceIndex: number;
  setCommandHint: Dispatch<SetStateAction<string | null>>;
  setCommandChoices: Dispatch<SetStateAction<SlashCommandChoicesState | null>>;
  setCommandScopeChoices: Dispatch<
    SetStateAction<SlashCommandScopeChoicesState | null>
  >;
  setCommandMultiChoices: Dispatch<
    SetStateAction<SlashCommandMultiChoicesState | null>
  >;
  setModelPopover: Dispatch<
    SetStateAction<SlashCommandModelPopoverState | null>
  >;
  setMultiSelected: Dispatch<SetStateAction<Set<string>>>;
  setAuthRun: Dispatch<SetStateAction<AuthRunRef | null>>;
  setSecretCommand: Dispatch<SetStateAction<SlashCommandSecretState | null>>;
  setSecretValue: Dispatch<SetStateAction<string>>;
  setExternalCommandConfirm: Dispatch<
    SetStateAction<{ command: SlashCommandRecord; args: string } | null>
  >;
  setSlashCommands: Dispatch<SetStateAction<SlashCommandRecord[]>>;
  setCommandChoiceIndex: Dispatch<SetStateAction<number>>;
  setSelected: Dispatch<SetStateAction<string[]>>;
  setText: Dispatch<SetStateAction<string>>;
  pendingSessionRoomModelsRef: MutableRefObject<string[] | null>;
  agentsPickerInitRef: MutableRefObject<boolean>;
  refreshSessionMeta: () => void;
  onRefreshHealth?: () => void | Promise<void>;
  handleStop: () => void;
};

export type RoomSlashExecute = {
  applySessionScopedModels: (composition: string[]) => void;
  executeSlashCommand: ExecuteSlashCommandFn;
  handleAuthRunComplete: () => Promise<void>;
  runSlashCommand: RunSlashCommandFn;
};

/** Slash command execution + auth flow — extracted from RoomChat (F9). */
export function useRoomSlashExecute(
  options: RoomSlashExecuteOptions,
): RoomSlashExecute {
  const {
    sessionId,
    activeSessionIdRef,
    agents,
    slashCommands,
    authRun,
    commandChoices,
    commandChoiceIndex,
    setCommandHint,
    setCommandChoices,
    setCommandScopeChoices,
    setCommandMultiChoices,
    setModelPopover,
    setMultiSelected,
    setAuthRun,
    setSecretCommand,
    setSecretValue,
    setExternalCommandConfirm,
    setSlashCommands,
    setCommandChoiceIndex,
    setSelected,
    setText,
    pendingSessionRoomModelsRef,
    agentsPickerInitRef,
    refreshSessionMeta,
    onRefreshHealth,
    handleStop,
  } = options;

  const applySessionScopedModels = useCallback(
    (composition: string[]) => {
      const comp = sortAgentIds(composition);
      if (comp.length === 0) return;
      pendingSessionRoomModelsRef.current = comp;
      writePendingRoomModels(comp);
      setSelected(comp);
      agentsPickerInitRef.current = true;
      setCommandHint(`이 세션 동안 ${comp.join(", ")} 에이전트를 사용합니다.`);
    },
    [
      agentsPickerInitRef,
      pendingSessionRoomModelsRef,
      setCommandHint,
      setSelected,
    ],
  );

  const executeSlashCommand = useCallback<ExecuteSlashCommandFn>(
    async (command, args, confirm = false) => {
      const sid = sessionId ?? activeSessionIdRef.current;
      const isGlobal = !sid && SESSIONLESS_ACCOUNT_COMMAND_IDS.has(command.id);
      if (!sid && !isGlobal) return;
      setCommandHint(null);
      setCommandChoices(null);
      setCommandScopeChoices(null);
      if (command.id !== "model") {
        setModelPopover(null);
      }
      try {
        const res = isGlobal
          ? await runGlobalCommand({
              command_id: command.id,
              args,
              confirm,
            })
          : await runSessionCommand(sid!, {
              command_id: command.id,
              args,
              confirm,
            });
        if (res.kind === "server") {
          const resultStage = res.result as
            | { stage?: unknown; auth_run?: unknown }
            | undefined;
          if (
            sid &&
            res.text &&
            !resultStage?.stage &&
            !resultStage?.auth_run
          ) {
            appendSessionMessages(
              resolveRunSessionKey(sessionId, activeSessionIdRef.current),
              [
                {
                  id: `slash-divider-${crypto.randomUUID()}`,
                  role: "system",
                  label: "",
                  body: `[slash] ${res.text}`,
                },
              ],
            );
          }
          if (sid) {
            refreshSessionMeta();
          } else if (isGlobal) {
            void onRefreshHealth?.();
          }
          setCommandHint(res.text ?? "명령 실행 완료");
        } else if (res.kind === "external") {
          const payload = res.result as
            | { stdout?: string; detail?: string }
            | undefined;
          setCommandHint(
            (payload?.stdout ?? payload?.detail ?? "외부 명령 실행됨").slice(
              0,
              240,
            ),
          );
        } else if (res.text) {
          setCommandHint(res.text.slice(0, 240));
        } else if (res.detail) {
          setCommandHint(res.detail);
        } else {
          setCommandHint("명령 실행됨");
        }
        const stage = res.result as
          | {
              prompt?: string;
              stage?: string;
              composition?: string[];
              auto?: boolean;
              provider?: string;
              choices?: {
                kind?: string;
                provider?: string;
                current?: string[];
                composition?: string[];
                options: {
                  value: string;
                  label: string;
                  sublabel?: string;
                  selected?: boolean;
                  ready?: boolean;
                }[];
              };
              input?: { kind?: string; prefill?: string };
              auth_run?: AuthRunRef;
              updated?: boolean;
              model_updated?: boolean;
            }
          | undefined;
        if (stage?.auth_run) {
          setAuthRun(stage.auth_run);
          setCommandChoices(null);
          setCommandMultiChoices(null);
          setCommandScopeChoices(null);
          setCommandHint(null);
        }
        if (stage?.choices?.options?.length) {
          setCommandChoiceIndex(0);
          const choices = stage.choices;
          const kind = choices.kind ?? "provider";
          if (kind === "model_provider") {
            setModelPopover((prev) => ({
              command,
              autoEnabled: Boolean(stage.auto ?? prev?.autoEnabled),
              agents: prev?.agents ?? [],
              sidePanel: prev?.sidePanel ?? null,
            }));
            setCommandChoices(null);
            setCommandMultiChoices(null);
            setCommandScopeChoices(null);
            void executeSlashCommand(command, "compose");
          } else if (kind === "model_preset" || kind === "model_panel") {
            const providerId = stage.provider ?? choices.provider ?? "";
            const providerLabel = stage.prompt ?? "";
            const panelChoices = choices as {
              options: {
                value: string;
                label: string;
                selected?: boolean;
                available?: boolean;
                coming_soon_note?: string;
              }[];
              efforts?: string[];
              selected_model?: string;
              selected_effort?: string;
            };
            const presets = panelChoices.options.map((opt) => ({
              value: opt.value,
              label: opt.label,
              selected: opt.selected,
              available: opt.available,
              comingSoonNote: opt.coming_soon_note,
            }));
            setModelPopover((prev) => {
              const sidePanel: ModelPopoverSidePanel = {
                providerId,
                providerLabel,
                presets,
                efforts: panelChoices.efforts,
                selectedModel: panelChoices.selected_model,
                selectedEffort: panelChoices.selected_effort,
              };
              if (prev) {
                return {
                  ...prev,
                  autoEnabled: Boolean(stage.auto ?? prev.autoEnabled),
                  sidePanel,
                };
              }
              return {
                command,
                autoEnabled: Boolean(stage.auto),
                agents: [],
                sidePanel,
              };
            });
            setCommandChoices(null);
            setCommandMultiChoices(null);
            setCommandScopeChoices(null);
          } else if (kind === "multi") {
            if (command.id === "model") {
              const modelAgents: ModelPopoverAgent[] = sortAgentPickerOptions(
                choices.options,
              ).map((opt) => ({
                value: opt.value,
                label: opt.label,
                ready: opt.ready,
              }));
              setMultiSelected(new Set(sortAgentIds(choices.current ?? [])));
              setModelPopover((prev) => ({
                command,
                autoEnabled: prev?.autoEnabled ?? false,
                agents: modelAgents,
                sidePanel: prev?.sidePanel ?? null,
              }));
              setCommandChoices(null);
              setCommandScopeChoices(null);
            } else {
              setCommandMultiChoices({
                command,
                argsPrefix: args,
                prompt: stage.prompt ?? res.text ?? "",
                current: sortAgentIds(stage.choices.current ?? []),
                options: sortAgentPickerOptions(stage.choices.options),
              });
              setMultiSelected(
                new Set(sortAgentIds(stage.choices.current ?? [])),
              );
              setCommandChoices(null);
              setCommandScopeChoices(null);
            }
          } else if (kind === "scope") {
            const composition =
              stage.composition ??
              stage.choices.composition ??
              args.split(",").filter(Boolean);
            setCommandScopeChoices({
              command,
              composition,
              prompt: stage.prompt ?? res.text ?? "",
              options: stage.choices.options,
            });
            setCommandMultiChoices(null);
            setCommandChoices(null);
          } else {
            setCommandChoices({
              command,
              argsPrefix: args,
              prompt: stage.prompt ?? res.text ?? "",
              kind,
              options: stage.choices.options,
            });
            setCommandMultiChoices(null);
            setCommandScopeChoices(null);
          }
          setCommandHint(null);
        } else {
          setCommandChoices(null);
          setCommandMultiChoices(null);
          setCommandScopeChoices(null);
        }
        if (stage?.updated && stage.composition?.length) {
          setSelected(sortAgentIds(stage.composition));
        }
        if (stage?.model_updated) {
          void onRefreshHealth?.();
        }
        if (stage?.input?.kind === "secret" && stage.input.prefill) {
          setSecretCommand({
            command,
            argsPrefix: stage.input.prefill.replace(/^\/login\s+/, ""),
            prompt: stage.prompt ?? "API 키 입력",
          });
          setSecretValue("");
          setText("");
          setCommandHint(null);
        } else if (stage?.input?.prefill) {
          setText(stage.input.prefill);
        } else if (command.id !== "model") {
          setText("");
        }
        void fetchCommands(isGlobal ? null : sid)
          .then((payload) => setSlashCommands(payload.commands ?? []))
          .catch(() => undefined);
      } catch (e) {
        const message = e instanceof Error ? e.message : "명령 실패";
        if (
          command.kind === "external" &&
          command.requires_human_confirm &&
          /confirm/i.test(message)
        ) {
          setExternalCommandConfirm({ command, args });
          return;
        }
        setCommandHint(message);
      }
    },
    [
      activeSessionIdRef,
      onRefreshHealth,
      refreshSessionMeta,
      sessionId,
      setAuthRun,
      setCommandChoiceIndex,
      setCommandChoices,
      setCommandHint,
      setCommandMultiChoices,
      setCommandScopeChoices,
      setExternalCommandConfirm,
      setModelPopover,
      setMultiSelected,
      setSecretCommand,
      setSecretValue,
      setSelected,
      setSlashCommands,
      setText,
    ],
  );

  const handleAuthRunComplete = useCallback(async () => {
    if (!authRun) return;
    const providerLabel =
      authRun.provider_id === "claude"
        ? "Claude"
        : authRun.provider_id === "codex"
          ? "Codex"
          : authRun.provider_id === "cursor"
            ? "Cursor"
            : authRun.provider_id;
    const actionLabel = authRun.action === "logout" ? "로그아웃" : "로그인";
    if (authRun.provider_id === "claude" && authRun.action === "login") {
      try {
        const res = await reconnectClaudeAuth();
        if (!sessionId) {
          setCommandHint(
            res.ok
              ? `${providerLabel} ${actionLabel} 완료`
              : (res.hint ?? `${providerLabel} ${actionLabel} 확인 필요`),
          );
          void fetchCommands(null)
            .then((payload) => setSlashCommands(payload.commands ?? []))
            .catch(() => undefined);
          void onRefreshHealth?.();
          return;
        }
        refreshSessionMeta();
        if (!res.ok && res.hint) {
          setCommandHint(res.hint);
        }
        return;
      } catch {
        /* fall through to generic completion hint */
      }
    }
    if (!sessionId) {
      setCommandHint(`${providerLabel} ${actionLabel} 완료`);
      void fetchCommands(null)
        .then((payload) => setSlashCommands(payload.commands ?? []))
        .catch(() => undefined);
      void onRefreshHealth?.();
      return;
    }
    refreshSessionMeta();
  }, [
    authRun,
    onRefreshHealth,
    refreshSessionMeta,
    sessionId,
    setCommandHint,
    setSlashCommands,
  ]);

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

  const runSlashCommand = useCallback<RunSlashCommandFn>(
    async (command, rawText) => {
      setCommandHint(null);
      if (authRun && (command.id === "login" || command.id === "logout")) {
        setCommandHint("진행 중인 인증 패널을 먼저 닫아주세요.");
        return;
      }
      if (command.kind === "client") {
        if (command.id === "stop") handleStop();
        if (command.id === "focus-composer") focusComposerInput();
        setText("");
        return;
      }
      const parsed = rawText
        ? matchSlashCommand(rawText, slashCommands)
        : command;
      const target = parsed ?? command;
      const args = rawText ? rawText.replace(/^\/[^\s]+\s*/, "").trim() : "";
      if (!sessionId) {
        if (target.id === "model") {
          if (args) {
            const modelParsed = parseModelSlashArgs(args);
            const hasComposition =
              args.includes(",") ||
              modelParsed.scope != null ||
              (modelParsed.composition.length > 0 &&
                !["claude", "codex", "cursor", "kimi"].includes(
                  modelParsed.composition[0]?.split("|")[0] ?? "",
                ));
            if (hasComposition) {
              const next = sortAgentIds(
                modelParsed.composition.filter((id) =>
                  agents.some((agent) => agent.id === id),
                ),
              );
              if (next.length === 0) {
                setText("");
                setCommandHint("선택 가능한 에이전트가 없습니다.");
                return;
              }
              if (modelParsed.scope === "default") {
                setText("");
                void runRoomSlash(
                  `/model compose ${next.join(",")} default`,
                ).then(() => {
                  setCommandHint(
                    `기본값으로 저장했습니다 (${next.join(", ")}).`,
                  );
                });
                return;
              }
              if (modelParsed.scope === "session") {
                setText("");
                applySessionScopedModels(next);
                return;
              }
              setCommandScopeChoices({
                command: target,
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
              setText("");
              return;
            }
          }
          setText("");
          await executeSlashCommand(target, args);
          return;
        }
        if (!SESSIONLESS_ACCOUNT_COMMAND_IDS.has(target.id)) return;
      }
      if (
        target.kind === "external" &&
        target.requires_human_confirm !== false
      ) {
        setExternalCommandConfirm({ command: target, args });
        return;
      }
      await executeSlashCommand(target, args);
    },
    [
      agents,
      applySessionScopedModels,
      authRun,
      executeSlashCommand,
      handleStop,
      sessionId,
      setCommandHint,
      setCommandScopeChoices,
      setExternalCommandConfirm,
      setText,
      slashCommands,
    ],
  );

  return {
    applySessionScopedModels,
    executeSlashCommand,
    handleAuthRunComplete,
    runSlashCommand,
  };
}
