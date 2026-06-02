/** Plan action / execute copy — refs and inline paths. */

export const PLAN_REF_BLOCK = /\(ref:\s*([^)]+)\)/gi;
export const CHAT_LINE_REF = /chat\.jsonl#L\s*(\d+)/gi;

export type ParsedPlanField = {
  /** Text with `(ref: …)` blocks removed. */
  body: string;
  /** Sorted unique chat.jsonl line numbers from refs. */
  refs: number[];
};

export function extractChatLineRefs(text: string): number[] {
  const refs = new Set<number>();
  CHAT_LINE_REF.lastIndex = 0;
  let match: RegExpExecArray | null;
  while ((match = CHAT_LINE_REF.exec(text)) !== null) {
    const line = Number(match[1]);
    if (line > 0) refs.add(line);
  }
  return [...refs].sort((a, b) => a - b);
}

export function stripPlanRefAnnotations(text: string): string {
  return text
    .replace(PLAN_REF_BLOCK, "")
    .replace(/\s{2,}/g, " ")
    .replace(/\s+([,.;])/g, "$1")
    .replace(/([(\[])\s+/g, "$1")
    .trim();
}

export function parsePlanField(text: string | undefined | null): ParsedPlanField | null {
  const raw = text?.trim();
  if (!raw) return null;
  return {
    body: stripPlanRefAnnotations(raw),
    refs: extractChatLineRefs(raw),
  };
}
