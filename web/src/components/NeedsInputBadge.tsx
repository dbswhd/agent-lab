import type { NeedsInputStatus } from "../utils/needsInputStatus";

type Props = {
  status: NeedsInputStatus;
  onOpen: () => void;
};

/** Header pill — Codex "Needs input" / CC agents "blocked on you". */
export function NeedsInputBadge({ status, onOpen }: Props) {
  if (!status.active) return null;
  return (
    <button
      type="button"
      className="workspace-chrome__pill workspace-chrome__pill--needs-input"
      data-testid="needs-input-badge"
      onClick={onOpen}
      title={status.detail || status.label}
      aria-label={`${status.label}: ${status.detail}`}
    >
      <span className="needs-input-badge__dot" aria-hidden />
      <span className="needs-input-badge__label">{status.label}</span>
      {status.count > 1 ? (
        <span className="needs-input-badge__count">{status.count}</span>
      ) : null}
    </button>
  );
}
