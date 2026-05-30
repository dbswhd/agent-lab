type Props = {
  checked: boolean;
  onChange: (on: boolean) => void;
  disabled?: boolean;
};

export function ComposerEfficiencyToggle({ checked, onChange, disabled }: Props) {
  return (
    <label
      className={`composer-efficiency-toggle${checked ? " is-on" : ""}`}
      title="구독 절약 · pin cap · 최근 4턴 · 짧은 응답 · 합의 모드 slim payload"
    >
      <span className="composer-efficiency-toggle__label">효율</span>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        className="composer-efficiency-switch"
        disabled={disabled}
        onClick={() => onChange(!checked)}
      >
        <span className="composer-efficiency-switch__thumb" aria-hidden />
      </button>
    </label>
  );
}
