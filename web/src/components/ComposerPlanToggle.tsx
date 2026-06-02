type Props = {
  checked: boolean;
  onChange: (on: boolean) => void;
  disabled?: boolean;
};

export function ComposerPlanToggle({ checked, onChange, disabled }: Props) {
  return (
    <label
      className={[
        "composer-plan-toggle",
        checked ? "composer-plan-toggle--on" : "",
      ]
        .filter(Boolean)
        .join(" ")}
      title="전송 후 plan.md 갱신"
    >
      <input
        type="checkbox"
        className="composer-plan-toggle__input"
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
      />
      <span className="composer-plan-toggle__label">정리</span>
    </label>
  );
}
