import type { ChatMessage, AgentRole } from "../utils/transcript";
import {
  actLabel,
  formatEnvelopeMeta,
  normalizeAct,
  shouldWarnMissingEnvelope,
} from "../utils/agentEnvelope";
import { transcriptInitial } from "../utils/transcriptMessageMarkers";

export function TranscriptIdentity({
  label,
  role,
}: {
  label: string;
  role: AgentRole;
}) {
  return (
    <span className="transcript-identity" aria-hidden>
      {transcriptInitial(label, role)}
    </span>
  );
}

export function TranscriptAuthorLine({ message }: { message: ChatMessage }) {
  const act = normalizeAct(message.envelope?.act);
  const meta = message.envelope ? formatEnvelopeMeta(message.envelope) : null;
  const round = Math.max(1, message.parallelRound ?? 1);
  const parts = [
    act ? actLabel(act) : null,
    meta,
    round > 1 ? `R${round}` : null,
  ].filter(Boolean);
  const showWarning = shouldWarnMissingEnvelope(
    message.parallelRound,
    message.envelope,
    message.envelopeParseError,
  );

  return (
    <div className="transcript-author-line">
      <strong className="transcript-author-name">{message.label}</strong>
      {parts.length > 0 ? (
        <span className="transcript-author-meta">{parts.join(" · ")}</span>
      ) : null}
      {showWarning ? (
        <span className="transcript-author-warning">envelope 없음</span>
      ) : null}
    </div>
  );
}

export function TranscriptMarkerStrip({
  markers,
}: {
  markers: readonly string[];
}) {
  if (markers.length === 0) return null;
  return (
    <div className="transcript-marker-strip" aria-label="Transcript markers">
      {markers.map((marker) => (
        <span key={marker} className="transcript-marker">
          {marker}
        </span>
      ))}
    </div>
  );
}
