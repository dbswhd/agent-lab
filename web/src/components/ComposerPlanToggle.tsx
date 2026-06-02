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
      title="켜면 메시지 전송 후 plan 문서를 갱신합니다 (plan 탭)"
    >
      <input
        type="checkbox"
        className="composer-plan-toggle__input"
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
      />
      <span className="composer-plan-toggle__label">전송 시 plan 갱신</span>
    </label>
  );
}
