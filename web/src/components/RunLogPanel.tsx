import { useEffect, useState } from "react";
import { fetchSessionEvidence, type EvidenceEntry } from "../api/client";
import { Avatar } from "./Avatar";
import { EvidenceTimeline } from "./EvidenceTimeline";
import { agentLabel } from "../utils/transcript";
import type { LiveMsg } from "../run/runSessionRegistry";
import type { AgentRole, ToolRunCard } from "../utils/transcript";
import { useLocale } from "../i18n/useLocale";

type Props = {
  sessionId?: string | null;
  turnMessages: LiveMsg[];
  running: boolean;
  active: { agent: string; round: number } | null;
  runningAgents?: { agent: string; round: number; label?: string }[];
  onStop?: () => void;
  longRunning?: boolean;
  runLockStuck?: boolean;
  releasingLock?: boolean;
  onReleaseLock?: () => void;
};

type RunLogEntry = {
  id: string;
  role: string;
  label?: string;
  text: string;
  ts?: string;
  kind: "tool" | "system" | "agent";
  toolCard?: ToolRunCard;
};

function entryType(role: string): "tool" | "system" | "agent" {
  if (role === "system") return "system";
  if (role === "tool") return "tool";
  return "agent";
}

function formatTs(ts?: string): string {
  if (!ts) return "—";
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return ts.slice(11, 19) || ts;
  return d.toLocaleTimeString(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function isToolActivityLine(text: string): boolean {
  return text.trimStart().toLowerCase().startsWith("[tool ·");
}

function formatDurationMs(startedAt?: number, doneAt?: number): string | null {
  if (!startedAt || !doneAt || doneAt <= startedAt) return null;
  const ms = doneAt - startedAt;
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

function RunLogToolCard({ card }: { card: ToolRunCard }) {
  const duration = formatDurationMs(card.startedAt, card.doneAt);
  return (
    <details
      className="run-entry__tool run-entry__tool--structured"
      open={false}
    >
      <summary className="run-entry__text run-entry__text--tool">
        <span className="run-entry__tool-name">{card.tool}</span>
        {card.args ? (
          <span className="run-entry__tool-args">{card.args}</span>
        ) : null}
        {duration ? (
          <span className="run-entry__tool-duration">{duration}</span>
        ) : null}
      </summary>
      {card.output ? (
        <pre className="run-entry__tool-body">{card.output}</pre>
      ) : (
        <p className="run-entry__tool-body run-entry__tool-body--empty">
          (no stdout)
        </p>
      )}
    </details>
  );
}

function RunLogEntryText({ entry }: { entry: RunLogEntry }) {
  if (entry.toolCard) {
    return <RunLogToolCard card={entry.toolCard} />;
  }
  if (entry.kind !== "tool" || !isToolActivityLine(entry.text)) {
    return (
      <span className="run-entry__text">
        {entry.label && entry.kind === "agent" ? `${entry.label}: ` : ""}
        {entry.text}
      </span>
    );
  }
  const match = entry.text.match(/^\[tool · ([^\]]+)\]\s*(.*)$/i);
  const toolName = match?.[1]?.trim() || "tool";
  const detail = match?.[2]?.trim() || "";
  return (
    <details className="run-entry__tool" open={false}>
      <summary className="run-entry__text run-entry__text--tool">
        <span className="run-entry__tool-name">{toolName}</span>
        {detail ? <span className="run-entry__tool-args">{detail}</span> : null}
      </summary>
      {detail ? <pre className="run-entry__tool-body">{detail}</pre> : null}
    </details>
  );
}

function expandRunLogEntries(
  turnMessages: LiveMsg[],
  waitingText: string,
): RunLogEntry[] {
  const out: RunLogEntry[] = [];
  for (const m of turnMessages) {
    if (m.roundDivider || m.role === "you") continue;
    const kind = entryType(m.role);
    const ts = (m as LiveMsg & { ts?: string }).ts;
    const label =
      m.label || (kind === "agent" ? agentLabel(m.role) : undefined);

    if (m.toolCards?.length) {
      for (const card of m.toolCards) {
        out.push({
          id: `${m.id}-tool-${card.id}`,
          role: m.role,
          label,
          text: `[tool · ${card.tool}] ${card.args ?? ""}`.trim(),
          ts,
          kind: "tool",
          toolCard: card,
        });
      }
    }

    if (m.activities?.length) {
      for (let i = 0; i < m.activities.length; i++) {
        const line = m.activities[i]?.trim();
        if (!line) continue;
        out.push({
          id: `${m.id}-act-${i}`,
          role: m.role,
          label,
          text: line,
          ts,
          kind: kind === "agent" ? "tool" : kind,
        });
      }
    }

    const body = m.body?.trim();
    if (body) {
      out.push({
        id: `${m.id}-body`,
        role: m.role,
        label,
        text: body,
        ts,
        kind,
      });
    } else if (m.typing && !m.activities?.length) {
      out.push({
        id: `${m.id}-typing`,
        role: m.role,
        label,
        text: waitingText,
        ts,
        kind,
      });
    } else if (kind === "system" && !body && !m.activities?.length) {
      continue;
    }
  }
  return out;
}

/** Run tab — prototype `run-log` / `run-entry` presentation. */
export function RunLogPanel({
  sessionId = null,
  turnMessages,
  running,
  active,
  runningAgents = [],
  onStop,
  longRunning,
  runLockStuck,
  releasingLock,
  onReleaseLock,
}: Props) {
  const { msg } = useLocale();
  const entries = expandRunLogEntries(turnMessages, msg.runLogWaiting);
  const [evidence, setEvidence] = useState<EvidenceEntry[]>([]);

  useEffect(() => {
    if (!sessionId) {
      setEvidence([]);
      return;
    }
    let cancelled = false;
    void fetchSessionEvidence(sessionId, 30)
      .then((payload) => {
        if (!cancelled) setEvidence(payload.entries ?? []);
      })
      .catch(() => {
        if (!cancelled) setEvidence([]);
      });
    return () => {
      cancelled = true;
    };
  }, [sessionId, running, entries.length]);

  return (
    <div className="run-log">
      <div className="run-log__head">
        <svg
          viewBox="0 0 24 24"
          width="14"
          height="14"
          fill="none"
          stroke="currentColor"
          strokeWidth={1.7}
          strokeLinecap="round"
          aria-hidden
        >
          <rect x="4" y="4" width="16" height="16" rx="2" />
          <path d="M9 9h6M9 13h6M9 17h4" />
        </svg>
        {msg.runLogTitle}
        {longRunning && running ? (
          <span className="badge badge--warn" style={{ marginLeft: 8 }}>
            {msg.runLogLongRun}
          </span>
        ) : null}
        {runLockStuck && onReleaseLock ? (
          <button
            type="button"
            className="plan-btn"
            style={{ marginLeft: "auto" }}
            disabled={releasingLock}
            onClick={onReleaseLock}
          >
            {releasingLock ? msg.runLogReleasingLock : msg.runLogReleaseLock}
          </button>
        ) : null}
        {running && onStop && !runLockStuck ? (
          <button
            type="button"
            className="plan-btn plan-btn--danger"
            style={{ marginLeft: "auto" }}
            onClick={onStop}
          >
            {msg.runLogStop}
          </button>
        ) : null}
      </div>

      {entries.length === 0 && !running ? (
        <div className="empty-state">
          <span className="empty-state__icon" aria-hidden>
            <svg
              viewBox="0 0 24 24"
              width="24"
              height="24"
              fill="none"
              stroke="currentColor"
              strokeWidth={1.5}
              strokeLinecap="round"
            >
              <rect x="4" y="4" width="16" height="16" rx="2" />
              <path d="M9 9h6M9 13h6" />
            </svg>
          </span>
          <span className="empty-state__title">{msg.runLogEmptyTitle}</span>
          <span className="empty-state__hint">{msg.runLogEmptyHint}</span>
        </div>
      ) : null}

      {running && runningAgents.length > 0 && entries.length === 0
        ? runningAgents.map((slot) => (
            <div
              key={`${slot.agent}-r${slot.round}`}
              className="run-entry run-entry--agent"
            >
              <span className="run-entry__ts">…</span>
              <Avatar role={slot.agent as AgentRole} size={20} />
              <span className="run-entry__type run-entry__type--agent">▸</span>
              <span className="run-entry__text">
                {msg.runLogWaitingRound(
                  slot.label ?? agentLabel(slot.agent),
                  slot.round,
                )}
              </span>
            </div>
          ))
        : null}

      {running &&
      active &&
      entries.length === 0 &&
      runningAgents.length === 0 ? (
        <div className={`run-entry run-entry--agent`}>
          <span className="run-entry__ts">…</span>
          <Avatar role={active.agent as AgentRole} size={20} />
          <span className="run-entry__type run-entry__type--agent">▸</span>
          <span className="run-entry__text">
            {msg.runLogWaitingRound(agentLabel(active.agent), active.round)}
          </span>
        </div>
      ) : null}

      {entries.map((entry) => {
        const agentRole =
          entry.kind === "agent" ? (entry.role as AgentRole) : undefined;
        return (
          <div key={entry.id} className={`run-entry run-entry--${entry.kind}`}>
            <span className="run-entry__ts">{formatTs(entry.ts)}</span>
            {agentRole ? (
              <Avatar role={agentRole} label={entry.label} size={20} />
            ) : null}
            <span className={`run-entry__type run-entry__type--${entry.kind}`}>
              {entry.kind === "tool"
                ? "$"
                : entry.kind === "system"
                  ? "✦"
                  : "▸"}
            </span>
            <RunLogEntryText entry={entry} />
          </div>
        );
      })}

      <EvidenceTimeline entries={evidence} compact />

      {!running && entries.length > 0 ? (
        <div className="run-log__done">
          <svg
            viewBox="0 0 16 16"
            width="13"
            height="13"
            fill="none"
            stroke="currentColor"
            strokeWidth={2}
            strokeLinecap="round"
            aria-hidden
          >
            <path d="M2 8l4 4 8-8" />
          </svg>
          {msg.runLogTurnComplete}
        </div>
      ) : null}
    </div>
  );
}
