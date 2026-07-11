import type { RuntimeOrchestration } from "../api/client";

/** Meta line for Work phase chip / status bar when plan/mission lanes drift. */
export function orchestrationDriftMetaLine(
  orchestration: RuntimeOrchestration | null | undefined,
): string | null {
  if (!orchestration?.phase_drift) return null;
  const hint = orchestration.reconcile_hint?.trim();
  if (hint) return `Orchestration drift · ${hint}`;
  const reason = orchestration.phase_drift_reason?.trim();
  if (reason) return `Orchestration drift · ${reason}`;
  return "Orchestration drift";
}

/** Prefer drift meta over plan meta when both are present. */
export function workPhaseMetaLine(
  orchestration: RuntimeOrchestration | null | undefined,
  planMetaLine: string | null | undefined,
): string | null {
  return orchestrationDriftMetaLine(orchestration) ?? planMetaLine ?? null;
}
