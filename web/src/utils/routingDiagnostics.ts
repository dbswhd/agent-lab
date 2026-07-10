export type RoutingDiagnosticsView = {
  readonly route: string;
  readonly source: string;
  readonly agents: readonly string[];
  readonly consensus: boolean;
  readonly runProfile: string;
};

function stringValue(value: unknown): string {
  return typeof value === "string" && value.trim() ? value.trim() : "—";
}

function agentList(value: unknown): readonly string[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((agent) =>
    typeof agent === "string" && agent.trim() ? [agent.trim()] : [],
  );
}

function isUnknownRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function buildRoutingDiagnostics(
  run?: Record<string, unknown> | null,
  runtimeRunProfile?: string | null,
): RoutingDiagnosticsView {
  const contract = isUnknownRecord(run?.turn_contract)
    ? run.turn_contract
    : null;
  const policy = isUnknownRecord(run?.turn_policy) ? run.turn_policy : null;
  const routing = isUnknownRecord(policy?.routing_contract)
    ? policy.routing_contract
    : null;

  return {
    route: stringValue(
      contract?.contract_id ?? routing?.route_category ?? run?.turn_profile,
    ),
    source: stringValue(contract?.source ?? policy?.scribe_trigger),
    agents: agentList(run?.agents),
    consensus: run?.consensus_mode === true,
    runProfile: stringValue(runtimeRunProfile ?? run?.run_profile),
  };
}
