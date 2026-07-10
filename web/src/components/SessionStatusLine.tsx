import type { StatusLineChip } from "../utils/sessionStatusLine";

type Props = {
  chips: StatusLineChip[];
};

/** Compact Autonomy × sandbox statusline chips (ABSORB P1-status). */
export function SessionStatusLine({ chips }: Props) {
  if (!chips.length) return null;
  return (
    <span
      className="session-status-line"
      data-testid="session-status-line"
      aria-label="Session status"
    >
      {chips.map((chip) => (
        <span
          key={chip.id}
          className="workspace-chrome__run-badge"
          title={chip.title ?? chip.label}
        >
          {chip.label}
        </span>
      ))}
    </span>
  );
}
