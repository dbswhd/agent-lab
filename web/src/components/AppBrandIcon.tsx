type Props = {
  className?: string;
};

/** Brand mark. Asset path preserved; styled via `.titlebar__logo` wrapper in parent. */
export function AppBrandIcon({ className = "app-brand-icon" }: Props) {
  return (
    <img
      className={className}
      src="/app-icon.png"
      srcSet="/app-icon.png 1x, /app-icon@2x.png 2x"
      alt=""
      width={16}
      height={16}
      decoding="async"
      draggable={false}
    />
  );
}
