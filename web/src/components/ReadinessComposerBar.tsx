import type { ReadinessResponse } from "../api/client";
import { ComposerStrip } from "./ComposerStrip";

type Props = {
  readiness: ReadinessResponse | null;
};

/** MB-9 — composer hint when readiness is warning/blocked (no model calls).
 *
 *  Renders via ComposerStrip; tone is danger when blocked, warn otherwise —
 *  previously both states shared undifferentiated styling (dead modifier
 *  classes with no matching CSS).
 */
export function ReadinessComposerBar({ readiness }: Props) {
  if (!readiness || readiness.verdict === "ready") return null;

  const blocked = readiness.verdict === "blocked";
  return (
    <ComposerStrip
      tone={blocked ? "danger" : "warn"}
      role="alert"
      ariaLabel="에이전트 준비 상태"
      title={blocked ? "Readiness blocked" : "Readiness warning"}
      description={
        readiness.next_actions.length === 0
          ? "왼쪽 rail 「연결」 또는 설정 → 연결을 확인하세요."
          : undefined
      }
      items={
        readiness.next_actions.length > 0 ? readiness.next_actions : undefined
      }
    />
  );
}
