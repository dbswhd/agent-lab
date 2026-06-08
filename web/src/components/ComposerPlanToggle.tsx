type Props = {
  checked: boolean;
  onChange: (on: boolean) => void;
  disabled?: boolean;
};

/**
 * Rebuilt plan toggle. Prop signature preserved.
 * New class system reuses `.switch` track from base.css.
 */
export function ComposerPlanToggle({ checked, onChange, disabled }: Props) {
  return (
    <label
      className={`switch${checked ? " is-on" : ""}`}
      title="켜면 메시지 전송 후 plan 문서를 갱신합니다 (plan 탭)"
    >
      <input
        type="checkbox"
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
      />
      <span className="switch__track" />
      <span>전송 시 plan 갱신</span>
    </label>
  );
}
