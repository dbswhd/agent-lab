import type { StatusLineChip } from "../utils/sessionStatusLine";

type Props = {
  chips: StatusLineChip[];
};

/** Compact Autonomy × sandbox × cost statusline chips (ABSORB P1-status + F8). */
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
          className={[
            "workspace-chrome__run-badge",
            chip.tone === "warn"
              ? "workspace-chrome__run-badge--warn"
              : chip.tone === "danger"
                ? "workspace-chrome__run-badge--danger"
                : undefined,
          ]
            .filter(Boolean)
            .join(" ")}
          title={chip.title ?? chip.label}
          data-testid={chip.id === "cost" ? "session-cost-chip" : undefined}
        >
          {chip.label}
        </span>
      ))}
    </span>
  );
}
