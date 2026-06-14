import { useEffect, useMemo, useState } from "react";
import { fetchSessionRuntime, type RuntimeSnapshot } from "../api/client";
import { useLocale } from "../i18n/useLocale";
import {
  buildHumanDecisionLanes,
  humanDecisionBlockedLanes,
  shouldShowHumanDecisionBanner,
} from "../utils/humanDecisionView";

type Props = {
  sessionId: string | null;
  reloadKey?: number;
  discussPaused?: boolean;
  compact?: boolean;
  onOpenInbox?: () => void;
};

export function HumanDecisionBanner({
  sessionId,
  reloadKey = 0,
  discussPaused = false,
  compact = false,
  onOpenInbox,
}: Props) {
  const { msg } = useLocale();
  const [runtime, setRuntime] = useState<RuntimeSnapshot | null>(null);

  useEffect(() => {
    if (!sessionId) {
      setRuntime(null);
      return;
    }
    let cancelled = false;
    void fetchSessionRuntime(sessionId)
      .then((snap) => {
        if (!cancelled) setRuntime(snap);
      })
      .catch(() => {
        if (!cancelled) setRuntime(null);
      });
    return () => {
      cancelled = true;
    };
  }, [sessionId, reloadKey, discussPaused]);

  const lanes = useMemo(
    () => buildHumanDecisionLanes(runtime, discussPaused),
    [runtime, discussPaused],
  );
  const blocked = useMemo(() => humanDecisionBlockedLanes(lanes), [lanes]);
  const visible = shouldShowHumanDecisionBanner(runtime, discussPaused);

  if (!visible || blocked.length === 0) return null;

  const profile = runtime?.gates?.gate_profile;

  return (
    <div
      className={[
        "human-decision-banner",
        compact ? "human-decision-banner--compact" : undefined,
      ]
        .filter(Boolean)
        .join(" ")}
      role="status"
    >
      <div className="human-decision-banner__body">
        <strong>{msg.humanDecisionTitle}</strong>
        <p className="human-decision-banner__hint">{msg.humanDecisionHint}</p>
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
        {profile ? (
          <span className="human-decision-banner__profile">
            {msg.humanDecisionProfile(profile)}
          </span>
        ) : null}
      </div>
      {onOpenInbox ? (
        <span className="human-decision-banner__actions">
          <button type="button" className="btn btn--sm btn--ok" onClick={onOpenInbox}>
            {msg.humanDecisionOpenInbox}
          </button>
        </span>
      ) : null}
    </div>
  );
}
