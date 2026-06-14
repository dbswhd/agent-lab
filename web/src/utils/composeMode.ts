import type { ComposerTurnProfile } from "./turnProfile";
import { normalizeTurnProfile } from "./turnProfile";

export type ComposeMode = "discuss" | "plan" | "execute";

/** Single composer control: turn profile + discuss/plan/execute. */
export type UnifiedComposerMode =
  | "quick"
  | "analyze"
  | "discuss"
  | "review"
  | "free"
  | "plan"
  | "execute";

const COMPOSE_STORAGE_KEY = "agent-lab-compose-mode";
const UNIFIED_STORAGE_KEY = "agent-lab-unified-compose-mode";

export const COMPOSE_MODE_OPTIONS: {
  id: ComposeMode;
  label: string;
  title: string;
}[] = [
  {
    id: "discuss",
    label: "토론",
    title: "에이전트 토론 — 턴 종료 시 plan.md 자동 갱신",
  },
  {
    id: "plan",
    label: "정리",
    title: "전송 후 plan.md 갱신",
  },
  {
    id: "execute",
    label: "실행",
    title: "plan 액션 dry-run → Cursor 파일 수정 → 승인",
  },
];

export const UNIFIED_MODE_OPTIONS: {
  id: UnifiedComposerMode;
  label: string;
  title: string;
  infinity?: boolean;
}[] = [
  {
    id: "quick",
    label: "빠른",
    title: "에이전트 1명 · 1라운드 · 짧게 확인",
  },
  {
    id: "analyze",
    label: "분석",
    title: "R1 병렬 · 현황·사실·근거만 · plan 유지",
  },
  {
    id: "discuss",
    label: "토론",
    title: "레거시 — 분석 모드로 대체됨",
  },
  {
    id: "review",
    label: "검토",
    title: "레거시 — ♾️ 모드 사용",
  },
  {
    id: "plan",
    label: "정리",
    title: "전송 후 plan.md 갱신",
  },
  {
    id: "execute",
    label: "실행",
    title: "plan 액션 dry-run → 승인",
  },
  {
    id: "free",
    label: "♾️",
    title: "R1 주장 → R2 반박 ↔ R3 확장 루프 → 「이의 없습니다」",
    infinity: true,
  },
];

/** Composer strategy seg — quick / discuss / ♾️ only. */
export const TURN_STRATEGY_OPTIONS = UNIFIED_MODE_OPTIONS.filter(
  (o) => o.id === "quick" || o.id === "analyze" || o.id === "free",
);

const PLAN_AFTER_SEND_KEY = "agent-lab-plan-after-send";
const PLAN_AFTER_SEND_SESSION_PREFIX = "agent-lab-plan-after-send:";

function planAfterSendSessionKey(sessionId: string): string {
  return `${PLAN_AFTER_SEND_SESSION_PREFIX}${sessionId}`;
}

export function getPlanAfterSendForSession(sessionId: string | null): boolean {
  if (sessionId) {
    try {
      const flag = localStorage.getItem(planAfterSendSessionKey(sessionId));
      if (flag === "1" || flag === "true") return true;
      if (flag === "0" || flag === "false") return false;
    } catch {
      /* fall through */
    }
  }
  return getPlanAfterSend();
}

export function setPlanAfterSendForSession(
  sessionId: string | null,
  on: boolean,
): void {
  if (sessionId) {
    try {
      localStorage.setItem(planAfterSendSessionKey(sessionId), on ? "1" : "0");
    } catch {
      /* ignore */
    }
  }
  setPlanAfterSend(on);
}

export function turnStrategyDescription(profile: ComposerTurnProfile): string {
  const normalized = normalizeTurnProfile(profile);
  return TURN_STRATEGY_OPTIONS.find((o) => o.id === normalized)?.title ?? "";
}

export function getPlanAfterSend(): boolean {
  try {
    const flag = localStorage.getItem(PLAN_AFTER_SEND_KEY);
    if (flag === "1" || flag === "true") return true;
    if (flag === "0" || flag === "false") return false;
    const unified = localStorage.getItem(UNIFIED_STORAGE_KEY);
    if (unified === "plan") return true;
    const legacyCompose = localStorage.getItem(COMPOSE_STORAGE_KEY);
    return legacyCompose === "plan";
  } catch {
    return false;
  }
}

export function setPlanAfterSend(on: boolean): void {
  localStorage.setItem(PLAN_AFTER_SEND_KEY, on ? "1" : "0");
  localStorage.setItem(COMPOSE_STORAGE_KEY, on ? "plan" : "discuss");
  const turn = getTurnProfileFromStorage();
  setUnifiedComposerMode(mergeToUnifiedMode(on ? "plan" : "discuss", turn));
}

function getTurnProfileFromStorage(): ComposerTurnProfile {
  return normalizeTurnProfile(localStorage.getItem("agent-lab-turn-profile"));
}

export function setTurnStrategy(profile: ComposerTurnProfile): void {
  const normalized = normalizeTurnProfile(profile);
  localStorage.setItem("agent-lab-turn-profile", normalized);
  setUnifiedComposerMode(
    mergeToUnifiedMode(getPlanAfterSend() ? "plan" : "discuss", normalized),
  );
}

export function getTurnStrategy(): ComposerTurnProfile {
  return normalizeTurnProfile(getTurnProfileFromStorage());
}

export function splitUnifiedMode(mode: UnifiedComposerMode): {
  composeMode: ComposeMode;
  turnProfile: ComposerTurnProfile;
} {
  switch (mode) {
    case "plan":
      return { composeMode: "plan", turnProfile: "analyze" };
    case "execute":
      return { composeMode: "execute", turnProfile: "analyze" };
    case "quick":
      return { composeMode: "discuss", turnProfile: "quick" };
    case "review":
      return { composeMode: "discuss", turnProfile: "review" };
    case "free":
      return { composeMode: "discuss", turnProfile: "free" };
    case "analyze":
    case "discuss":
    default:
      return { composeMode: "discuss", turnProfile: "analyze" };
  }
}

export function mergeToUnifiedMode(
  composeMode: ComposeMode,
  turnProfile: ComposerTurnProfile,
): UnifiedComposerMode {
  if (composeMode === "plan") return "plan";
  if (composeMode === "execute") return "execute";
  if (turnProfile === "quick") return "quick";
  if (turnProfile === "review") return "free";
  if (turnProfile === "free") return "free";
  if (normalizeTurnProfile(turnProfile) === "analyze") return "analyze";
  return "analyze";
}

export function unifiedModeDescription(mode: UnifiedComposerMode): string {
  if (mode === "plan") {
    return "전송 후 plan.md 갱신 (composer 정리 토글)";
  }
  if (mode === "execute") {
    return "plan 탭에서 dry-run · 승인";
  }
  return UNIFIED_MODE_OPTIONS.find((o) => o.id === mode)?.title ?? "";
}

export function getComposeMode(): ComposeMode {
  return splitUnifiedMode(getUnifiedComposerMode()).composeMode;
}

export function setComposeMode(mode: ComposeMode): void {
  const current = getUnifiedComposerMode();
  const { turnProfile } = splitUnifiedMode(current);
  setUnifiedComposerMode(mergeToUnifiedMode(mode, turnProfile));
}

export function getUnifiedComposerMode(): UnifiedComposerMode {
  try {
    const unified = localStorage.getItem(UNIFIED_STORAGE_KEY);
    if (
      unified === "quick" ||
      unified === "analyze" ||
      unified === "discuss" ||
      unified === "review" ||
      unified === "free" ||
      unified === "plan" ||
      unified === "execute"
    ) {
      const turnRaw =
        unified === "review"
          ? "free"
          : unified === "discuss"
            ? "analyze"
            : unified === "plan" || unified === "execute"
              ? "analyze"
              : unified;
      return mergeToUnifiedMode(
        unified === "plan"
          ? "plan"
          : unified === "execute"
            ? "execute"
            : "discuss",
        normalizeTurnProfile(turnRaw),
      );
    }
    const legacyCompose = localStorage.getItem(COMPOSE_STORAGE_KEY);
    const legacyTurn = localStorage.getItem("agent-lab-turn-profile");
    const compose: ComposeMode =
      legacyCompose === "plan" || legacyCompose === "execute"
        ? legacyCompose
        : "discuss";
    const turn: ComposerTurnProfile = normalizeTurnProfile(legacyTurn);
    return mergeToUnifiedMode(compose, turn);
  } catch {
    /* ignore */
  }
  return "analyze";
}

export function setUnifiedComposerMode(mode: UnifiedComposerMode): void {
  localStorage.setItem(UNIFIED_STORAGE_KEY, mode);
  const { composeMode, turnProfile } = splitUnifiedMode(mode);
  localStorage.setItem(COMPOSE_STORAGE_KEY, composeMode);
  localStorage.setItem("agent-lab-turn-profile", turnProfile);
}

export function composeModeSendLabel(mode: ComposeMode): string {
  switch (mode) {
    case "plan":
      return "정리 후 보내기";
    case "execute":
      return "dry-run 실행";
    default:
      return "보내기";
  }
}

export function unifiedModeSendLabel(mode: UnifiedComposerMode): string {
  const { composeMode } = splitUnifiedMode(mode);
  return composeModeSendLabel(composeMode);
}
