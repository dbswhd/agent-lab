import { useMemo, useState } from "react";
import type { SlashCommandRecord } from "../api/client";
import {
  defaultSlashGroupOpen,
  groupSlashCommands,
  SLASH_COMMAND_GROUP_LABELS,
  SLASH_COMMAND_GROUP_ORDER,
  type SlashCommandGroupKey,
} from "../utils/slashCommandGroups";

type Props = {
  commands: SlashCommandRecord[];
  onCopy?: (slash: string) => void;
  copiedSlash?: string | null;
  onPrefillSlash?: (slash: string) => void;
  variant?: "settings" | "panel";
  /** Cap rows per agent group (Settings); 0 = no cap */
  maxPerAgentGroup?: number;
  emptyHint?: string;
};

function commandBadge(cmd: SlashCommandRecord): string {
  if (cmd.scope === "external" || cmd.kind === "external") return "external";
  if (cmd.agent) return cmd.agent;
  return "built-in";
}

function CommandRow({
  cmd,
  onCopy,
  copied,
}: {
  cmd: SlashCommandRecord;
  onCopy?: (slash: string) => void;
  copied: string | null;
}) {
  const src = commandBadge(cmd);
  const badgeClass =
    src === "built-in" ? "ok" : src === "external" ? "accent" : "accent";
  return (
    <div
      className={`command-row${cmd.enabled === false ? " command-row--disabled" : ""}`}
    >
      <code className="command-row__cmd">{cmd.slash}</code>
      <span className="command-row__desc">
        {cmd.description ?? cmd.label}
        {cmd.enabled === false && cmd.disabled_reason ? (
          <span className="command-row__meta"> — {cmd.disabled_reason}</span>
        ) : null}
      </span>
      <span className={`badge badge--${badgeClass}`}>{src}</span>
      {onCopy ? (
        <button
          type="button"
          className="icon-btn"
          title="복사"
          onClick={() => onCopy(cmd.slash)}
        >
          {copied === cmd.slash ? "✓" : "⎘"}
        </button>
      ) : null}
    </div>
  );
}

export function SlashCommandGroupList({
  commands,
  onCopy,
  copiedSlash = null,
  onPrefillSlash,
  variant = "settings",
  maxPerAgentGroup = 0,
  emptyHint = "등록된 slash 명령이 없습니다.",
}: Props) {
  const groups = useMemo(() => groupSlashCommands(commands), [commands]);
  const [open, setOpen] = useState<Record<SlashCommandGroupKey, boolean>>(() =>
    defaultSlashGroupOpen(groups),
  );

  const total = SLASH_COMMAND_GROUP_ORDER.reduce(
    (n, key) => n + groups[key].length,
    0,
  );
  if (total === 0) {
    return <p className="settings-hint">{emptyHint}</p>;
  }

  return (
    <div className="commands-list commands-list--grouped">
      {SLASH_COMMAND_GROUP_ORDER.map((key) => {
        const rows = groups[key];
        if (rows.length === 0) return null;
        const isAgent = key !== "built_in" && key !== "external";
        const expanded = open[key];
        const cap =
          isAgent && maxPerAgentGroup > 0 ? maxPerAgentGroup : rows.length;
        const visible = expanded ? rows.slice(0, cap) : [];
        const hidden = rows.length - visible.length;

        return (
          <section
            key={key}
            className="plugin-agent-group commands-list__group"
          >
            <button
              type="button"
              className={[
                "plugin-agent-group__head",
                isAgent ? "" : "plugin-agent-group__head--static",
              ]
                .filter(Boolean)
                .join(" ")}
              aria-expanded={isAgent ? expanded : undefined}
              onClick={
                isAgent
                  ? () => setOpen((prev) => ({ ...prev, [key]: !prev[key] }))
                  : undefined
              }
              disabled={!isAgent}
            >
              {isAgent ? (
                <span className="plugin-agent-group__chevron" aria-hidden>
                  {expanded ? "▾" : "▸"}
                </span>
              ) : null}
              <span className="plugin-agent-group__name">
                {SLASH_COMMAND_GROUP_LABELS[key]}
              </span>
              <span className="badge">{rows.length}</span>
            </button>
            {expanded ? (
              <>
                {isAgent ? (
                  <p className="plugin-panel__hint commands-list__group-hint">
                    allowlist는 Plugins 탭에서 관리합니다.
                  </p>
                ) : null}
                {variant === "panel" ? (
                  <ul className="plugin-panel__list">
                    {visible.map((cmd) => (
                      <li key={cmd.id}>
                        <button
                          type="button"
                          className="plugin-panel__cmd"
                          disabled={cmd.enabled === false}
                          onClick={() => onPrefillSlash?.(cmd.slash)}
                        >
                          <code>{cmd.slash}</code>
                          <span>{cmd.description ?? cmd.label}</span>
                        </button>
                      </li>
                    ))}
                  </ul>
                ) : (
                  visible.map((cmd) => (
                    <CommandRow
                      key={cmd.id}
                      cmd={cmd}
                      onCopy={onCopy}
                      copied={copiedSlash}
                    />
                  ))
                )}
                {hidden > 0 ? (
                  <p className="plugin-panel__hint commands-list__group-hint">
                    외 {hidden}개 — PluginPanel Commands 탭에서 전체 목록
                  </p>
                ) : null}
              </>
            ) : isAgent ? (
              <p className="plugin-panel__hint commands-list__group-hint">
                {rows.length}개 플러그인 slash — 펼쳐서 일부만 표시
              </p>
            ) : null}
          </section>
        );
      })}
    </div>
  );
}
