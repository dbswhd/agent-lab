import type { PlanActionItem } from "../api/client";
import {
  consensusDryRunActionTitle,
  consensusDryRunGateNotice,
} from "../utils/consensusAgreement";
import { AppBrandIcon } from "./AppBrandIcon";

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

export function ConsensusDryRunGateBar({
  proposal,
  busy,
  disabled,
  onDryRun,
  onOpenPlan,
  onDismiss,
}: Props) {
  const notice = consensusDryRunGateNotice(
    proposal.excerpt,
    proposal.summary,
    proposal.notice,
  );
  const actionTitle = consensusDryRunActionTitle(proposal.recommended);
  const canDryRun = Boolean(proposal.has_executable && proposal.action_key);

  return (
    <div
      className="mac-notification mac-notification--banner consensus-dry-run-gate-bar"
      role="region"
      aria-label="합의 plan 반영 · dry-run 확인"
    >
      <AppBrandIcon className="mac-notification-icon" />
      <div className="mac-notification-body">
        <div className="mac-notification-title">{notice}</div>
        {canDryRun && actionTitle ? (
          <div className="mac-notification-desc">추천 액션: {actionTitle}</div>
        ) : (
          <div className="mac-notification-desc">
            실행 가능한 plan 액션이 없습니다.
          </div>
        )}
        <div className="consensus-dry-run-gate-bar__actions">
          {canDryRun ? (
            <button
              type="button"
              className="mac-btn-primary consensus-dry-run-gate-bar__primary"
              disabled={disabled || busy}
              onClick={() => void onDryRun()}
            >
              {busy ? "시작 중…" : "dry-run 실행"}
            </button>
          ) : null}
          <button
            type="button"
            className="mac-btn-secondary"
            disabled={disabled}
            onClick={onOpenPlan}
          >
            plan 보기
          </button>
          <button
            type="button"
            className="mac-btn-secondary consensus-dry-run-gate-bar__later"
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
