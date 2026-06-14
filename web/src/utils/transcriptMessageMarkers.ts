import type { ChatMessage, AgentRole } from "./transcript";
import { normalizeAct } from "./agentEnvelope";

export function transcriptInitial(label: string, role: AgentRole): string {
  if (role === "you") return "H";
  return (label.trim()[0] ?? role[0] ?? "?").toUpperCase();
}

export function getTranscriptMarkers(message: ChatMessage): readonly string[] {
  const act = normalizeAct(message.envelope?.act);
  const refs = message.envelope?.refs ?? [];
  const markers: string[] = [];

  if (act === "BLOCK") {
    markers.push("Review blocker");
  } else if (act === "CHALLENGE") {
    markers.push("Review needed");
  } else if (act === "AMEND" || act === "PROPOSE") {
    markers.push("Plan update");
  }

  if (refs.length > 0) {
    markers.push("Plan ref");
  }

  return markers;
}
