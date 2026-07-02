import {
  formatSlashDividerLabel,
  parseSlashDividerParts,
} from "../utils/formatSlashDividerLabel";

type Props = {
  readonly text: string;
  readonly className?: string;
};

/** Slash command feedback — same chrome as round dividers in the transcript. */
export function SlashCommandDivider({ text, className }: Props) {
  const label = formatSlashDividerLabel(text);
  if (!label) return null;

  const parts = parseSlashDividerParts(text);

  return (
    <div
      className={["round-divider", "round-divider--slash", className]
        .filter(Boolean)
        .join(" ")}
      role="status"
      aria-label={label}
    >
      {parts ? (
        <span className="round-divider__content">
          <span className="round-divider__command">{parts.command}</span>
          <span className="round-divider__detail">{parts.message}</span>
        </span>
      ) : (
        <span className="round-divider__label">{label}</span>
      )}
    </div>
  );
}
