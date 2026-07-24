import type { NeedsInputStatus } from "../utils/needsInputStatus";

type Props = {
  status: NeedsInputStatus;
  onOpen: () => void;
};

function formatWaitAge(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const opened = Date.parse(iso);
  if (!Number.isFinite(opened)) return null;
  const sec = Math.max(0, Math.floor((Date.now() - opened) / 1000));
  if (sec < 60) return `${sec}s`;
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min}m`;
  const hr = Math.floor(min / 60);
  return `${hr}h`;
}

/** Header pill — Codex "Needs input" / CC agents "blocked on you". */
export function NeedsInputBadge({ status, onOpen }: Props) {
  if (!status.active) return null;
  const age = formatWaitAge(status.waitingSince);
  return (
    <button
      type="button"
      className="workspace-chrome__pill workspace-chrome__pill--needs-input"
      data-testid="needs-input-badge"
      onClick={onOpen}
      title={
        age
          ? `${status.detail || status.label} · ${age}`
          : status.detail || status.label
      }
      aria-label={`${status.label}: ${status.detail}${age ? ` (${age})` : ""}`}
    >
      <span className="needs-input-badge__dot" aria-hidden />
      <span className="needs-input-badge__label">{status.label}</span>
      {age ? (
        <span className="needs-input-badge__age" data-testid="needs-input-age">
          {age}
        </span>
      ) : null}
      {status.count > 1 ? (
        <span className="needs-input-badge__count">{status.count}</span>
      ) : null}
    </button>
  );
}
