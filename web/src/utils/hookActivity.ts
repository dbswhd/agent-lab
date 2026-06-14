export type HookEventPayload = {
  event?: string;
  blocked?: boolean;
  feedback?: string;
  sub_reason?: string;
};

export function isExecutionRelevantHook(
  event: string,
  blocked: boolean,
  _feedback?: string,
): boolean {
  const e = event.trim().toLowerCase();
  if (e === "pre_execute" && blocked) return true;
  if (e === "pre_verify" && blocked) return true;
  if (e.includes("contract") && blocked) return true;
  if (e === "response_contract_invalid") return true;
  if (blocked && (e.includes("verify") || e.includes("execute"))) return true;
  return false;
}

export function formatHookActivityLine(ev: HookEventPayload): string {
  const eventName = String(ev.event ?? "hook");
  const tag = ev.blocked ? "blocked" : "warn";
  const detail =
    (typeof ev.feedback === "string" && ev.feedback.trim()) ||
    (typeof ev.sub_reason === "string" && ev.sub_reason.trim()) ||
    eventName;
  return `[hook · ${eventName} · ${tag}] ${detail.slice(0, 160)}`;
}

export function formatDispatchActivityLine(payload: Record<string, unknown>): string {
  const op = String(payload.op ?? payload.status ?? "dispatch");
  const agents = Array.isArray(payload.agents)
    ? (payload.agents as string[]).join(",")
    : String(payload.agent ?? "");
  const id = String(payload.dispatch_id ?? "");
  return `[dispatch · ${op}] ${id}${agents ? ` · ${agents}` : ""}`.slice(0, 160);
}

export function formatEnvelopeActivityLine(
  round: number,
  opts: { hasAct?: boolean; parseError?: boolean },
): string | null {
  if (round < 2) return null;
  if (opts.parseError) {
    return "[envelope · parse_error] R2+ fence/JSON invalid";
  }
  if (!opts.hasAct) {
    return "[envelope · missing] R2+ act required";
  }
  return null;
}
