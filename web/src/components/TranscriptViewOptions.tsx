import { useLocale } from "../i18n/useLocale";

type Props = {
  showHumanSynthesis: boolean;
  showPeerChannel: boolean;
  onHumanSynthesisChange: (on: boolean) => void;
  onPeerChannelChange: (on: boolean) => void;
};

export function TranscriptViewOptions({
  showHumanSynthesis,
  showPeerChannel,
  onHumanSynthesisChange,
  onPeerChannelChange,
}: Props) {
  const { msg, locale } = useLocale();
  const peerDisabled = showHumanSynthesis;
  const peerDisabledTitle =
    locale === "ko"
      ? "Human 요약이 켜져 있으면 동료 채널을 볼 수 없습니다."
      : "Turn off Human summary to show the peer channel.";

  return (
    <div
      className="transcript-view-options"
      role="toolbar"
      aria-label={msg.transcriptViewOptions}
    >
      <label
        className="transcript-view-options__item"
        title={msg.humanSummaryHint}
      >
        <input
          type="checkbox"
          checked={showHumanSynthesis}
          onChange={(e) => onHumanSynthesisChange(e.target.checked)}
        />
        <span>{msg.humanSummary}</span>
      </label>
      <label
        className={`transcript-view-options__item${peerDisabled ? " is-disabled" : ""}`}
        title={peerDisabled ? peerDisabledTitle : msg.peerChannelHint}
      >
        <input
          type="checkbox"
          checked={showPeerChannel}
          disabled={peerDisabled}
          onChange={(e) => onPeerChannelChange(e.target.checked)}
        />
        <span>{msg.peerChannel}</span>
      </label>
    </div>
  );
}
