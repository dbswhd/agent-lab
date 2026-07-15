import { useId, useState } from "react";
import type { PlanExecutionOracleRecord } from "../api/client";

type Props = {
  oracle: PlanExecutionOracleRecord | null | undefined;
  ko?: boolean;
};

const VERDICT_LABEL_KO: Record<string, string> = {
  pass: "통과",
  fail: "실패",
  skipped: "건너뜀",
};

const VERDICT_LABEL_EN: Record<string, string> = {
  pass: "Pass",
  fail: "Fail",
  skipped: "Skipped",
};

/**
 * §7.3 (11-ui-ux-surface-map.md) — surface Oracle verdict/detail evidence on
 * the workspace card, mirroring MergeChecksPanel's collapse/auto-expand UX.
 */
export function OracleEvidencePanel({ oracle, ko = true }: Props) {
  const panelId = useId();
  const verdict = oracle?.verdict;
  const needsAttention = verdict === "fail";
  const [expanded, setExpanded] = useState(needsAttention);

  if (!verdict) return null;
  const open = expanded || needsAttention;
  const labels = ko ? VERDICT_LABEL_KO : VERDICT_LABEL_EN;
  const verdictLabel = labels[verdict] ?? verdict;

  return (
    <section
      className={[
        "oracle-evidence",
        open ? "oracle-evidence--expanded" : "oracle-evidence--collapsed",
        `oracle-evidence--${verdict}`,
      ].join(" ")}
      data-testid="oracle-evidence-panel"
    >
      <button
        type="button"
        className="oracle-evidence__toggle"
        aria-expanded={open}
        aria-controls={panelId}
        disabled={needsAttention}
        onClick={() => setExpanded((prev) => !prev)}
      >
        <span className="oracle-evidence__title">Oracle</span>
        <span
          className={[
            "oracle-evidence__verdict",
            `oracle-evidence__verdict--${verdict}`,
          ].join(" ")}
        >
          {verdictLabel}
        </span>
        {!needsAttention ? (
          <span
            className={[
              "oracle-evidence__chevron",
              open ? "oracle-evidence__chevron--open" : "",
            ]
              .filter(Boolean)
              .join(" ")}
            aria-hidden
          />
        ) : null}
      </button>
      {open ? (
        <div id={panelId} className="oracle-evidence__body">
          {oracle?.verify_criterion ? (
            <p className="oracle-evidence__row">
              <span className="oracle-evidence__label">
                {ko ? "검증 기준" : "Verify criterion"}
              </span>
              <span className="oracle-evidence__value">
                {oracle.verify_criterion}
              </span>
            </p>
          ) : null}
          {oracle?.detail ? (
            <p
              className={[
                "oracle-evidence__row",
                verdict === "fail" ? "oracle-evidence__row--fail" : "",
              ]
                .filter(Boolean)
                .join(" ")}
            >
              <span className="oracle-evidence__label">
                {ko ? "상세" : "Detail"}
              </span>
              <span className="oracle-evidence__value">{oracle.detail}</span>
            </p>
          ) : null}
          {oracle?.checked_paths?.length ? (
            <p className="oracle-evidence__row">
              <span className="oracle-evidence__label">
                {ko ? "검사 경로" : "Checked paths"}
              </span>
              <span className="oracle-evidence__value">
                {oracle.checked_paths.join(", ")}
              </span>
            </p>
          ) : null}
          {oracle?.checked_at ? (
            <p className="oracle-evidence__row">
              <span className="oracle-evidence__label">
                {ko ? "확인 시각" : "Checked at"}
              </span>
              <time
                className="oracle-evidence__value"
                dateTime={oracle.checked_at}
              >
                {oracle.checked_at.slice(11, 19)}
              </time>
            </p>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
