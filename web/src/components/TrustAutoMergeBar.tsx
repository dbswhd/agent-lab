import { useCallback, useEffect, useState } from "react";
import {
  fetchAutoMergeEligibility,
  postAutoMerge,
  type AutoMergeEligibilityPayload,
} from "../api/client";
import { useLocale } from "../i18n/useLocale";

type Props = {
  readonly sessionId: string;
  readonly executionId: string | null | undefined;
  readonly onMerged?: () => void;
};

export function TrustAutoMergeBar({ sessionId, executionId, onMerged }: Props) {
  const { t } = useLocale();
  const [eligibility, setEligibility] =
    useState<AutoMergeEligibilityPayload | null>(null);
  const [busy, setBusy] = useState(false);
  const [hint, setHint] = useState<string | null>(null);

  const load = useCallback(() => {
    if (!executionId) {
      setEligibility(null);
      return;
    }
    void fetchAutoMergeEligibility(sessionId, executionId)
      .then(setEligibility)
      .catch(() => setEligibility(null));
  }, [sessionId, executionId]);

  useEffect(() => {
    load();
  }, [load]);

  if (!eligibility || eligibility.gate_profile !== "assistant") return null;

  const remaining = eligibility.trust_budget?.auto_merge_remaining ?? 0;
  const total = eligibility.trust_budget?.auto_merge_total ?? 0;

  const runAutoMerge = async () => {
    if (!executionId || !eligibility.eligible) return;
    setBusy(true);
    setHint(null);
    try {
      await postAutoMerge(sessionId, executionId);
      setHint(t("saved"));
      onMerged?.();
      load();
    } catch (err) {
      setHint(err instanceof Error ? err.message : "auto-merge failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="trust-auto-merge-bar">
      <span className="ctx-oracle-badge ctx-oracle-badge--progress">
        {t("trustBudgetRemaining")}: {remaining}/{total}
      </span>
      {eligibility.eligible ? (
        <button
          type="button"
          className="btn btn--sm btn--ok"
          disabled={busy}
          onClick={() => void runAutoMerge()}
        >
          {t("autoMergeRun")}
        </button>
      ) : (
        <span className="settings-hint">{eligibility.reason ?? ""}</span>
      )}
      {hint ? <span className="settings-hint">{hint}</span> : null}
    </div>
  );
}
