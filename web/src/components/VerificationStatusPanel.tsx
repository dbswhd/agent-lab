import type {
  VerificationLaneId,
  VerificationLaneReport,
  VerificationReport,
  VerificationStatus,
} from "../api/client";

const LANE_ORDER: readonly VerificationLaneId[] = [
  "fast",
  "integration",
  "bridge",
  "ci_full",
];

function assertNever(value: never): never {
  throw new Error(`Unhandled verification value: ${value}`);
}

function statusLabel(status: VerificationStatus): string {
  switch (status) {
    case "passed":
      return "통과";
    case "failed":
      return "실패";
    case "not_run":
      return "미실행";
    case "running":
      return "실행 중";
    case "unknown":
      return "알 수 없음";
    default:
      return assertNever(status);
  }
}

function statusTone(status: VerificationStatus): "ok" | "fail" | "pending" {
  switch (status) {
    case "passed":
      return "ok";
    case "failed":
      return "fail";
    case "not_run":
    case "running":
    case "unknown":
      return "pending";
    default:
      return assertNever(status);
  }
}

function shortLaneLabel(lane: VerificationLaneId): string {
  switch (lane) {
    case "fast":
      return "Fast";
    case "integration":
      return "Int";
    case "bridge":
      return "Br";
    case "ci_full":
      return "CI";
    case "live":
      return "Live";
    default:
      return assertNever(lane);
  }
}

function durationLabel(seconds: number | null): string {
  if (seconds === null) return "duration 없음";
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  return `${Math.round(seconds / 60)}m`;
}

function ageLabel(finishedAt: string | null): string {
  if (!finishedAt) return "아직 실행 기록 없음";
  const time = Date.parse(finishedAt);
  if (Number.isNaN(time)) return finishedAt;
  const minutes = Math.max(0, Math.round((Date.now() - time) / 60_000));
  if (minutes < 1) return "방금 전";
  if (minutes < 60) return `${minutes}분 전`;
  return `${Math.round(minutes / 60)}시간 전`;
}

function countLabel(row: VerificationLaneReport): string {
  if (row.selected_count === null || row.total_count === null) {
    return "count 없음";
  }
  return `${row.selected_count}/${row.total_count}`;
}

type Props = {
  readonly report?: VerificationReport | null;
};

export function VerificationStatusPanel({ report }: Props) {
  const rows = LANE_ORDER.map((lane) => report?.lanes[lane]).filter(
    (row): row is VerificationLaneReport => Boolean(row),
  );

  if (rows.length === 0) {
    return (
      <section className="verification-status" aria-label="Verification status">
        <div className="verification-status__head">
          <span className="verification-status__title">Verify</span>
          <span className="verification-status__meta">not run</span>
        </div>
        <p className="verification-status__empty">
          아직 로컬 검증 report가 없습니다. <code>make test-fast</code> 또는{" "}
          <code>make ci-full</code> 실행 후 표시됩니다.
        </p>
      </section>
    );
  }

  return (
    <section className="verification-status" aria-label="Verification status">
      <div className="verification-status__head">
        <span className="verification-status__title">Verify</span>
        <span className="verification-status__meta">
          {report?.generated_at
            ? ageLabel(report.generated_at)
            : "local report"}
        </span>
      </div>
      <div className="verification-status__rows">
        {rows.map((row) => {
          const tone = statusTone(row.status);
          return (
            <details
              key={row.lane}
              className={`verification-status__row verification-status__row--${tone}`}
            >
              <summary>
                <span
                  className={`dot dot--${tone === "ok" ? "ok dot--live" : "warn"}`}
                />
                <span className="verification-status__lane">
                  <span className="verification-status__lane-full">
                    {row.label}
                  </span>
                  <span className="verification-status__lane-short">
                    {shortLaneLabel(row.lane)}
                  </span>
                </span>
                <span
                  className={`badge badge--${tone === "ok" ? "ok" : tone === "fail" ? "danger" : "warn"}`}
                >
                  {statusLabel(row.status)}
                </span>
                <span className="verification-status__summary">
                  {ageLabel(row.finished_at)} ·{" "}
                  {durationLabel(row.duration_seconds)} · {countLabel(row)}
                </span>
              </summary>
              <div className="verification-status__detail">
                <code>{row.command}</code>
                {row.marker_expression ? (
                  <span>marker: {row.marker_expression}</span>
                ) : null}
                {row.failure_summary ? (
                  <span>{row.failure_summary}</span>
                ) : null}
                {row.report_path ? <span>{row.report_path}</span> : null}
              </div>
            </details>
          );
        })}
      </div>
    </section>
  );
}
