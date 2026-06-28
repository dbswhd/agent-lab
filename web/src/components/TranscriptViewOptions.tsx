import { useLocale } from "../i18n/useLocale";

type Props = {
  showPeerChannel: boolean;
  onPeerChannelChange: (on: boolean) => void;
};

export function TranscriptViewOptions({
  showPeerChannel,
  onPeerChannelChange,
}: Props) {
  const { msg } = useLocale();

  return (
    <div
      className="transcript-view-options"
      role="toolbar"
      aria-label={msg.transcriptViewOptions}
    >
      <label
        className="transcript-view-options__item"
        title={msg.peerChannelHint}
      >
        <input
          type="checkbox"
          checked={showPeerChannel}
          onChange={(e) => onPeerChannelChange(e.target.checked)}
        />
        <span>{msg.peerChannel}</span>
      </label>
    </div>
  );
}
