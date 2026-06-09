import type { ReadinessResponse } from "../api/client";

type Props = {
  readiness: ReadinessResponse | null;
};

/** MB-9 — composer hint when readiness is warning/blocked (no model calls). */
export function ReadinessComposerBar({ readiness }: Props) {
  if (!readiness || readiness.verdict === "ready") return null;

  const blocked = readiness.verdict === "blocked";
  return (
    <div
      className={[
        "preflight-bar",
        blocked ? "preflight-bar--blocked" : "preflight-bar--warn",
      ].join(" ")}
      role="alert"
    >
      <span className="preflight-bar__title">
        {blocked ? "Readiness blocked" : "Readiness warning"}
      </span>
      {readiness.next_actions.length > 0 ? (
        <ul className="preflight-bar__list">
          {readiness.next_actions.map((action) => (
            <li key={action}>{action}</li>
          ))}
        </ul>
      ) : (
        <p className="preflight-bar__hint">
          Settings에서 에이전트 연결 상태를 확인하세요.
        </p>
      )}
    </div>
  );
}
