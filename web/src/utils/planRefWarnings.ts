import type { ChatLine } from "../api/client";

/** Minimum meaningful tokens in a plan item before we warn. */
const MIN_PLAN_TOKENS = 4;

const STOPWORDS = new Set([
  "the",
  "and",
  "that",
  "this",
  "for",
  "with",
  "from",
  "are",
  "was",
  "were",
  "have",
  "has",
  "had",
  "not",
  "but",
  "can",
  "will",
  "you",
  "your",
  "our",
  "ref",
  "chat",
  "jsonl",
  "plan",
  "md",
  "이",
  "가",
  "은",
  "는",
  "을",
  "를",
  "에",
  "의",
  "로",
  "과",
  "와",
  "도",
  "만",
  "등",
  "및",
  "또",
  "것",
  "수",
  "등",
]);

const REF_BLOCK_RE = /\(ref:\s*([^)]+)\)/gi;
const LINE_NUM_RE = /L(\d+)/gi;
const TOKEN_RE = /[a-zA-Z0-9가-힣]{2,}/g;

export type PlanRefWarning = {
  planLine: number;
  snippet: string;
  refs: number[];
  sharedCount: number;
  overlapScore: number;
};

export type PlanRefWarningsView = {
  warnings: PlanRefWarning[];
  totalRefItems: number;
  bannerText: string | null;
};

function stripRefs(text: string): string {
  return text.replace(/\(ref:[^)]*\)/gi, "");
}

function tokenize(text: string): Set<string> {
  const cleaned = stripRefs(text)
    .replace(/[*`#|]/g, " ")
    .replace(/\s+/g, " ");
  const tokens = new Set<string>();
  for (const m of cleaned.matchAll(TOKEN_RE)) {
    const t = m[0].toLowerCase();
    if (!STOPWORDS.has(t)) tokens.add(t);
  }
  return tokens;
}

function overlapScore(
  planTokens: Set<string>,
  refTokens: Set<string>,
): { shared: number; score: number } {
  if (planTokens.size === 0 || refTokens.size === 0) {
    return { shared: 0, score: 0 };
  }
  let shared = 0;
  for (const t of planTokens) {
    if (refTokens.has(t)) shared += 1;
  }
  const score = shared / Math.min(planTokens.size, refTokens.size);
  return { shared, score };
}

/** Conservative heuristic — informational only, not a hard invalidation. */
function isSuspicious(
  planTokens: Set<string>,
  refTokens: Set<string>,
): boolean {
  if (planTokens.size < MIN_PLAN_TOKENS) return false;
  const { shared, score } = overlapScore(planTokens, refTokens);
  if (shared >= 2) return false;
  if (shared === 1 && score >= 0.08) return false;
  if (shared === 0) return true;
  return score < 0.06;
}

function extractRefLineNumbers(refBlock: string): number[] {
  const nums: number[] = [];
  for (const m of refBlock.matchAll(LINE_NUM_RE)) {
    nums.push(Number(m[1]));
  }
  return nums;
}

function chatContentAt(chat: ChatLine[] | undefined, lineNum: number): string {
  if (!chat || lineNum < 1 || lineNum > chat.length) return "";
  return chat[lineNum - 1]?.content ?? "";
}

function snippet(text: string, max = 72): string {
  const one = stripRefs(text).replace(/\s+/g, " ").trim();
  if (one.length <= max) return one;
  return `${one.slice(0, max - 1)}…`;
}

export function analyzePlanRefWarnings(
  planMd: string,
  chat: ChatLine[] | undefined,
): PlanRefWarningsView {
  if (!planMd.trim() || !chat?.length) {
    return { warnings: [], totalRefItems: 0, bannerText: null };
  }

  const warnings: PlanRefWarning[] = [];
  let totalRefItems = 0;
  const lines = planMd.split("\n");

  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i];
    if (!/\(ref:/i.test(line) || /\(ref:\s*불명확\)/i.test(line)) continue;

    const planTokens = tokenize(line);
    if (planTokens.size === 0) continue;

    const refs: number[] = [];
    for (const m of line.matchAll(REF_BLOCK_RE)) {
      refs.push(...extractRefLineNumbers(m[1]));
    }
    if (refs.length === 0) continue;

    totalRefItems += 1;
    const refText = refs.map((n) => chatContentAt(chat, n)).join("\n");
    const refTokens = tokenize(refText);
    const { shared, score } = overlapScore(planTokens, refTokens);

    if (isSuspicious(planTokens, refTokens)) {
      warnings.push({
        planLine: i + 1,
        snippet: snippet(line),
        refs: [...new Set(refs)],
        sharedCount: shared,
        overlapScore: score,
      });
    }
  }

  let bannerText: string | null = null;
  if (warnings.length > 0) {
    const n = warnings.length;
    bannerText =
      `출처(ref)와 항목 내용의 키워드 겹침이 낮은 항목 ${n}개 — ` +
      `chat.jsonl에서 직접 확인해 주세요. (정보용 경고, plan 항목은 그대로 유효합니다)`;
  }

  return { warnings, totalRefItems, bannerText };
}
