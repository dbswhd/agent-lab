import type { BackgroundRunInfo } from "../run/runSessionRegistry";
import { useLocale } from "../i18n/useLocale";

type Props = {
  info: BackgroundRunInfo;
  onStop?: () => void;
};

/** Server-side run lock without live SSE typing (mission / execute / retry). */
export function BackgroundRunStrip({ info, onStop }: Props) {
  const { msg } = useLocale();
  const kindLabel = msg.backgroundRunKind(info.runKind);

  return (
    <div
      className="live-agents-strip live-agents-strip--background"
      role="status"
      aria-live="polite"
    >
      <span className="live-agents-strip__chip live-agents-strip__chip--background">
        <span className="dot dot--live" aria-hidden />
        <span className="live-agents-strip__name">{kindLabel}</span>
        <span className="live-agents-strip__detail">{info.label}</span>
        {onStop ? (
          <button
            type="button"
            className="btn btn--xs live-agents-strip__stop"
            onClick={onStop}
          >
            {msg.backgroundRunStop}
          </button>
        ) : null}
      </span>
    </div>
  );
}
