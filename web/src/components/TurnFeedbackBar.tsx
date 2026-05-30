import type { ComposerTurnProfile } from "../utils/turnProfile";
import { profileLabel } from "../utils/turnProfileBandit";

type Props = {
  profile: ComposerTurnProfile;
  partial?: boolean;
  onVote: (vote: "up" | "down") => void;
  disabled?: boolean;
};

export function TurnFeedbackBar({
  profile,
  partial,
  onVote,
  disabled,
}: Props) {
  return (
    <div className="turn-feedback-bar" role="group" aria-label="턴 결과 피드백">
      <span className="turn-feedback-bar__prompt">
        {partial ? "부분 저장된" : "이번"} {profileLabel(profile)} 턴 — 도움이 됐나요?
      </span>
      <div className="turn-feedback-bar__actions">
        <button
          type="button"
          className="turn-feedback-btn turn-feedback-btn--up"
          disabled={disabled}
          aria-label="도움이 됐어요"
          onClick={() => onVote("up")}
        >
          👍
        </button>
        <button
          type="button"
          className="turn-feedback-btn turn-feedback-btn--down"
          disabled={disabled}
          aria-label="별로였어요"
          onClick={() => onVote("down")}
        >
          👎
        </button>
      </div>
    </div>
  );
}
