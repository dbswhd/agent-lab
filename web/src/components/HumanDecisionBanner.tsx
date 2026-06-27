import { useEffect } from "react";
import type { RuntimeSnapshot } from "../api/client";
import { useLocale } from "../i18n/useLocale";
import { useHumanDecisionRuntime } from "../hooks/useHumanDecisionRuntime";
import type { HumanDecisionLane } from "../utils/humanDecisionView";

type Props = {
  sessionId: string | null;
  reloadKey?: number;
  discussPaused?: boolean;
  compact?: boolean;
  headline?: string;
  detail?: string;
  onOpenInbox?: () => void;
  onVisibleChange?: (visible: boolean) => void;
};

export function HumanDecisionBanner({
  sessionId,
  reloadKey = 0,
  discussPaused = false,
  compact = false,
  headline,
  detail,
  onOpenInbox,
  onVisibleChange,
}: Props) {
  const { msg } = useLocale();
  const { runtime, blocked, visible } = useHumanDecisionRuntime(
    sessionId,
    reloadKey,
    discussPaused,
  );

  useEffect(() => {
    onVisibleChange?.(visible);
  }, [onVisibleChange, visible]);

  if (!visible) return null;

  return (
    <HumanDecisionBannerView
      runtime={runtime}
      blocked={blocked}
      compact={compact}
      headline={headline}
      detail={detail}
      onOpenInbox={onOpenInbox}
      msg={msg}
    />
  );
}

function HumanDecisionBannerView({
  runtime,
  blocked,
  compact,
  headline,
  detail,
  onOpenInbox,
  msg,
}: {
  runtime: RuntimeSnapshot | null;
  blocked: HumanDecisionLane[];
  compact?: boolean;
  headline?: string;
  detail?: string;
  onOpenInbox?: () => void;
  msg: ReturnType<typeof useLocale>["msg"];
}) {
  const profile = runtime?.gates?.gate_profile;
  const useCompactCopy = Boolean(headline);

  return (
    <div
      className={[
        "human-decision-banner",
        compact ? "human-decision-banner--compact" : undefined,
        useCompactCopy ? "human-decision-banner--headline" : undefined,
      ]
        .filter(Boolean)
        .join(" ")}
      role="status"
    >
      <div className="human-decision-banner__body">
        {useCompactCopy ? (
          <>
            <strong>{headline}</strong>
            {detail ? (
              <p className="human-decision-banner__hint">{detail}</p>
            ) : null}
          </>
        ) : (
          <>
            <strong>{msg.humanDecisionTitle}</strong>
            <p className="human-decision-banner__hint">
              {msg.humanDecisionHint}
            </p>
            <ul className="human-decision-banner__lanes">
              {blocked.map((lane) => (
                <li key={lane.id}>
                  <span className="human-decision-banner__lane-label">
                    {lane.id === "discuss"
                      ? msg.humanDecisionLaneDiscuss
                      : lane.id === "plan"
                        ? msg.humanDecisionLanePlan
                        : msg.humanDecisionLaneExecute}
                  </span>
                  <span className="human-decision-banner__lane-state">
                    {msg.humanDecisionBlocked}
                  </span>
                  {lane.reason ? (
                    <span className="human-decision-banner__lane-reason">
                      {msg.humanDecisionReason(lane.reason)}
                    </span>
                  ) : null}
                </li>
              ))}
            </ul>
          </>
        )}
        {profile ? (
          <span className="human-decision-banner__profile">
            {msg.humanDecisionProfile(profile)}
          </span>
        ) : null}
      </div>
      {onOpenInbox ? (
        <span className="human-decision-banner__actions">
          <button
            type="button"
            className="btn btn--sm btn--ok"
            onClick={onOpenInbox}
          >
            {msg.humanDecisionOpenInbox}
          </button>
        </span>
      ) : null}
    </div>
  );
}
