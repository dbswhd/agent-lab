/** Extract 1-based chat.jsonl line refs from plan.md provenance markers. */

const REF_RE = /\(ref:\s*chat\.jsonl#L(\d+)/gi;

export function extractPlanChatRefs(planMd: string): number[] {
  const lines = new Set<number>();
  let match: RegExpExecArray | null;
  REF_RE.lastIndex = 0;
  while ((match = REF_RE.exec(planMd)) !== null) {
    const n = Number(match[1]);
    if (Number.isFinite(n) && n > 0) lines.add(n);
  }
  return [...lines].sort((a, b) => a - b);
}
