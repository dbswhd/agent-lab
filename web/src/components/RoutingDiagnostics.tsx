import { useEffect, useState } from "react";
import { fetchSessionRuntime } from "../api/client";
import { useLocale } from "../i18n/useLocale";
import { buildRoutingDiagnostics } from "../utils/routingDiagnostics";
import { agentLabel } from "../utils/transcript";

type Props = {
  readonly sessionId: string | null;
  readonly run?: Record<string, unknown> | null;
};

export function RoutingDiagnostics({ sessionId, run }: Props) {
  const { locale } = useLocale();
  const ko = locale === "ko";
  const [runProfile, setRunProfile] = useState<string | null>(null);

  useEffect(() => {
    if (!sessionId) {
      setRunProfile(null);
      return;
    }
    let cancelled = false;
    void fetchSessionRuntime(sessionId)
      .then((runtime) => {
        if (!cancelled) setRunProfile(runtime.status_line?.run_profile ?? null);
      })
      .catch(() => {
        if (!cancelled) setRunProfile(null);
      });
    return () => {
      cancelled = true;
    };
  }, [sessionId]);

  const view = buildRoutingDiagnostics(run, runProfile);
  const roster = view.agents.length
    ? view.agents.map(agentLabel).join(" · ")
    : "—";

  return (
    <section className="ctx-section">
      <div className="ctx-section__label">
        {ko ? "라우팅 상세" : "Routing details"}
      </div>
      <dl className="ctx-diagnostic-list">
        <div>
          <dt>{ko ? "경로" : "Route"}</dt>
          <dd>{view.route}</dd>
        </div>
        <div>
          <dt>{ko ? "선택 근거" : "Source"}</dt>
          <dd>{view.source}</dd>
        </div>
        <div>
          <dt>{ko ? "참여 에이전트" : "Roster"}</dt>
          <dd>{roster}</dd>
        </div>
        <div>
          <dt>{ko ? "합의 검토" : "Consensus"}</dt>
          <dd>
            {view.consensus ? (ko ? "사용" : "On") : ko ? "미사용" : "Off"}
          </dd>
        </div>
        <div>
          <dt>{ko ? "실행 프로필" : "Run profile"}</dt>
          <dd>{view.runProfile}</dd>
        </div>
      </dl>
    </section>
  );
}
