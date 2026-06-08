type Props = {
  checked: boolean;
  onChange: (on: boolean) => void;
  disabled?: boolean;
  label?: string;
};

/** Efficiency toggle — prototype `.switch` + checkbox track. */
export function ComposerEfficiencyToggle({
  checked,
  onChange,
  disabled,
  label = "Efficiency",
}: Props) {
  return (
    <label className="switch" title="구독 절약 · pin cap · 최근 4턴 · 짧은 응답">
      <input
        type="checkbox"
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
      />
      <span className="switch__track" aria-hidden />
      {label}
    </label>
  );
}
