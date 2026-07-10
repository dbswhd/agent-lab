import type { RuntimeSnapshot } from "../api/client";
import { useLocale } from "../i18n/useLocale";
import { useSessionRuntime } from "../hooks/useSessionRuntime";
import { buildRoutingDiagnostics } from "../utils/routingDiagnostics";
import { agentLabel } from "../utils/transcript";

type Props = {
  readonly sessionId: string | null;
  readonly run?: Record<string, unknown> | null;
  /** Parent-provided runtime — skips local `/runtime` fetch when defined. */
  runtimeSnapshot?: RuntimeSnapshot | null;
};

function consensusLabel(enabled: boolean, ko: boolean): string {
  if (enabled) return ko ? "사용" : "On";
  return ko ? "미사용" : "Off";
}

export function RoutingDiagnostics({ sessionId, run, runtimeSnapshot }: Props) {
  const { locale } = useLocale();
  const ko = locale === "ko";
  const ownsRuntimeFetch = runtimeSnapshot === undefined;
  const { runtime: fetchedRuntime } = useSessionRuntime(sessionId, {
    run,
    enabled: ownsRuntimeFetch,
  });
  const runtime = ownsRuntimeFetch ? fetchedRuntime : runtimeSnapshot;
  const runProfile = runtime?.status_line?.run_profile ?? null;

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
          <dd>{consensusLabel(view.consensus, ko)}</dd>
        </div>
        <div>
          <dt>{ko ? "실행 프로필" : "Run profile"}</dt>
          <dd>{view.runProfile}</dd>
        </div>
      </dl>
    </section>
  );
}
