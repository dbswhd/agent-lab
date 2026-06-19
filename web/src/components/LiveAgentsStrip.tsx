import type { RunningAgentSlot } from "../run/runningAgents";
import { useLocale } from "../i18n/useLocale";

type Props = {
  slots: RunningAgentSlot[];
  running: boolean;
};

/** Visible on every workspace tab while a turn is in flight. */
export function LiveAgentsStrip({ slots, running }: Props) {
  const { msg } = useLocale();
  if (!running || slots.length === 0) return null;

  return (
    <div className="live-agents-strip" role="status" aria-live="polite">
      {slots.map((slot) => {
        const activity = slot.activity;
        return (
          <span
            key={`${slot.agent}-r${slot.round}`}
            className={`live-agents-strip__chip live-agents-strip__chip--${slot.agent}`}
          >
            <span className="dot dot--live" aria-hidden />
            <span className="live-agents-strip__name">
              {slot.label} · R{slot.round}
            </span>
            <span className="live-agents-strip__detail">
              {activity ?? msg.liveAgentsResponding}
            </span>
          </span>
        );
      })}
    </div>
  );
}
