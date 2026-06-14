type Props = {
  checked: boolean;
  onChange: (on: boolean) => void;
  disabled?: boolean;
  label?: string;
  title?: string;
};

/** Plan mode — per-send toggle (4C: decide at composer, not at session create). */
export function ComposerPlanToggle({
  checked,
  onChange,
  disabled,
  label = "Plan",
  title = "Clarify → plan.md → Human 승인 → execute",
}: Props) {
  return (
    <label className={`switch${checked ? " is-on" : ""}`} title={title}>
      <input
        type="checkbox"
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
      />
      <span className="switch__track" />
      <span>{label}</span>
    </label>
  );
}
