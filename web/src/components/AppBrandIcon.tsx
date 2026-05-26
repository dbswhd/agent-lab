type Props = {
  className?: string;
};

/** Titlebar / in-app brand mark — 16pt with 32/64px assets for crisp rendering. */
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
