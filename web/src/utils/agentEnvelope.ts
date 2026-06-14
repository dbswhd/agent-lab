import type { AgentEnvelope } from "./transcript";

export type EnvelopeAct =
  | "PROPOSE"
  | "AMEND"
  | "ENDORSE"
  | "CHALLENGE"
  | "PASS"
  | "BLOCK";

export const ACT_LABELS: Record<EnvelopeAct, string> = {
  PROPOSE: "제안",
  AMEND: "수정",
  ENDORSE: "동의",
  CHALLENGE: "이의",
  PASS: "PASS",
  BLOCK: "BLOCK",
};

export const COMPACT_ACTS = new Set<EnvelopeAct>(["ENDORSE", "PASS"]);

export function normalizeAct(act: string | undefined): EnvelopeAct | null {
  if (!act) return null;
  const key = act.toUpperCase() as EnvelopeAct;
  return key in ACT_LABELS ? key : null;
}

export function actLabel(act: string): string {
  const key = normalizeAct(act);
  return key ? ACT_LABELS[key] : act.toUpperCase();
}

export function formatEnvelopeMeta(envelope: AgentEnvelope): string | null {
  const parts: string[] = [];
  if (typeof envelope.confidence === "number") {
    parts.push(`${Math.round(envelope.confidence * 100)}%`);
  }
  if (envelope.refs?.length) {
    parts.push(envelope.refs.join(", "));
  }
  return parts.length ? parts.join(" · ") : null;
}

export function shouldWarnMissingEnvelope(
  parallelRound: number | undefined,
  envelope: AgentEnvelope | undefined,
  envelopeParseError?: boolean,
): boolean {
  return (
    (parallelRound ?? 1) >= 2 && (!envelope?.act || envelopeParseError === true)
  );
}
