import type { PlanActionItem } from "../api/client";
import {
  consensusDryRunActionTitle,
  consensusDryRunGateNotice,
} from "../utils/consensusAgreement";

export type ConsensusDryRunProposal = {
  excerpt?: string;
  summary?: string;
  notice?: string;
  recommended?: PlanActionItem | null;
  has_executable?: boolean;
  action_key?: string | null;
};

type Props = {
  proposal: ConsensusDryRunProposal;
  busy?: boolean;
  disabled?: boolean;
  onDryRun: () => void | Promise<void>;
  onOpenPlan: () => void;
  onDismiss: () => void;
};

/** ConsensusDryRunGateBar — banner shown after ♾️ consensus round completes.
 *
 *  Uses .consensus-gate-bar / .consensus-gate-bar__* classes (overlays.css).
 *  Drop-in for old component that used .mac-notification--banner (macos26.css).
 *
 *  Shows: notice text · recommended action title ·
 *         dry-run / plan 보기 / 나중에 buttons.
 *  dry-run button hidden when has_executable is false.
 */
export function ConsensusDryRunGateBar({
  proposal,
  busy,
  disabled,
  onDryRun,
  onOpenPlan,
  onDismiss,
}: Props) {
  const notice      = consensusDryRunGateNotice(
    proposal.excerpt,
    proposal.summary,
    proposal.notice,
  );
  const actionTitle = consensusDryRunActionTitle(proposal.recommended);
  const canDryRun   = Boolean(proposal.has_executable && proposal.action_key);

  return (
    <div
      className="consensus-gate-bar"
      role="region"
      aria-label="합의 plan 반영 · dry-run 확인"
    >
      {/* Codex-tinted icon */}
      <span className="consensus-gate-bar__icon" aria-hidden="true">
        <svg width="15" height="15" viewBox="0 0 20 20" fill="none">
          <path d="M10 2l2.5 5 5.5.8-4 3.9.95 5.5L10 14.75 5.05 17.2 6 11.7 2 7.8l5.5-.8L10 2z"
            stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
        </svg>
      </span>

      <div className="consensus-gate-bar__body">
        <div className="consensus-gate-bar__title">{notice}</div>

        {canDryRun && actionTitle ? (
          <div className="consensus-gate-bar__desc">
            추천 액션: {actionTitle}
          </div>
        ) : (
          <div className="consensus-gate-bar__desc">
            실행 가능한 plan 액션이 없습니다.
          </div>
        )}

        <div className="consensus-gate-bar__actions">
          {canDryRun ? (
            <button
              type="button"
              className="btn btn--primary btn--sm"
              disabled={disabled || busy}
              onClick={() => void onDryRun()}
            >
              {busy ? "시작 중…" : "dry-run 실행"}
            </button>
          ) : null}

          <button
            type="button"
            className="btn btn--sm"
            disabled={disabled}
            onClick={onOpenPlan}
          >
            plan 보기
          </button>

          <button
            type="button"
            className="btn btn--ghost btn--sm"
            disabled={disabled || busy}
            onClick={onDismiss}
          >
            나중에
          </button>
        </div>
      </div>
    </div>
  );
}
