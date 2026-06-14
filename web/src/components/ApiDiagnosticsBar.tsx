import { useCallback, useEffect, useState } from "react";
import type { DiagnosticsResponse } from "../api/client";
import { fetchDiagnostics } from "../api/client";

type Props = {
  /** true when backend /health returned OK */
  apiOk: boolean;
  /** sessions directory from server (overrides diag if provided) */
  sessionsDir: string | null;
  /** true when Cursor bridge probe failed */
  probeBridgeFailed: boolean;
};

/** ApiDiagnosticsBar — expanded panel inside the rail health chip.
 *
 *  Uses .diag-bar / .diag-bar__* classes (layout.css + overlays.css extensions).
 *  Drop-in for old component that used .api-diagnostics-bar (legacy-bridge.css).
 *
 *  Features:
 *  - Offline banner when apiOk === false
 *  - Cursor bridge failure hint
 *  - Sessions dir display
 *  - Expandable "진단 도구" section: refresh · copy JSON
 *  - Boot log tail (collapsible <details>)
 *
 *  Polls every 8 s when offline; stops polling when back online.
 */
export function ApiDiagnosticsBar({
  apiOk,
  sessionsDir,
  probeBridgeFailed,
}: Props) {
  const [diag,    setDiag]    = useState<DiagnosticsResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [copied,  setCopied]  = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setDiag(await fetchDiagnostics());
    } catch {
      setDiag(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
    if (apiOk) return;
    const id = window.setInterval(() => void load(), 8_000);
    return () => window.clearInterval(id);
  }, [apiOk, load]);

  async function copyJson() {
    if (!diag) return;
    try {
      await navigator.clipboard.writeText(JSON.stringify(diag, null, 2));
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2_000);
    } catch {
      /* ignore */
    }
  }

  const bootPath      = diag?.boot_log_path
    ?? "~/Library/Logs/Agent Lab/agent-lab-boot.log";
  const displaySessions = sessionsDir ?? diag?.sessions_dir ?? null;

  return (
    <div className="diag-bar" aria-label="API diagnostics">

      {displaySessions ? (
        <p className="diag-bar__sessions" title={displaySessions}>
          세션: {displaySessions}
        </p>
      ) : null}

      {!apiOk ? (
        <p className="diag-bar__offline">
          API 연결 끊김 — <code>make dev</code> 또는 앱 재시작 후 ↻ 새로고침
        </p>
      ) : null}

      {probeBridgeFailed ? (
        <p className="diag-bar__hint">
          Cursor bridge 실패 —{" "}
          <code>~/.agent-lab/.env</code>에{" "}
          <code>CURSOR_SDK_BRIDGE_BIN</code> 절대 경로 설정.{" "}
          <code>docs/STABILITY.md</code> 참고.
        </p>
      ) : null}

      <details className="diag-bar__detail">
        <summary>진단 도구</summary>

        <div className="diag-bar__actions">
          <button
            type="button"
            className="btn btn--sm"
            disabled={loading}
            onClick={() => void load()}
          >
            {loading ? "…" : "진단 새로고침"}
          </button>
          <button
            type="button"
            className="btn btn--sm"
            disabled={!diag}
            onClick={() => void copyJson()}
          >
            {copied ? "복사됨 ✓" : "진단 JSON 복사"}
          </button>
        </div>

        {diag?.auth_bootstrap_line ? (
          <p className="diag-bar__hint" title="최근 API 시작 시 Room auth bootstrap">
            {diag.auth_bootstrap_line}
          </p>
        ) : null}

        {diag?.bridge_audit ? (
          <div className="diag-bar__bridge" role="status">
            <span className="diag-bar__bridge-title">Bridge registry</span>
            <span className="diag-bar__bridge-meta">
              rows={diag.bridge_audit.record_count ?? 0} · active=
              {diag.bridge_audit.active_count ?? 0} · stale=
              {diag.bridge_audit.stale_count ?? 0} · orphan=
              {diag.bridge_audit.orphan_process_count ?? 0}
            </span>
            {(diag.bridge_audit.stale_records ?? []).slice(0, 3).map((row) => (
              <span key={`${row.workspace}-${row.pid}`} className="diag-bar__bridge-row">
                stale · {row.workspace} · pid {row.pid ?? "—"}
              </span>
            ))}
            {(diag.bridge_audit.orphan_processes ?? []).slice(0, 2).map((row) => (
              <span key={row.pid} className="diag-bar__bridge-row">
                orphan pid {row.pid} · {(row.command ?? "").slice(0, 60)}
              </span>
            ))}
          </div>
        ) : null}

        {diag?.boot_log_tail?.length ? (
          <details className="diag-bar__boot">
            <summary>
              부트 로그 (최근 {diag.boot_log_tail.length}줄)
            </summary>
            <p className="diag-bar__path" title={bootPath}>
              {bootPath}
            </p>
            <pre className="diag-bar__log">
              {diag.boot_log_tail.join("\n")}
            </pre>
          </details>
        ) : (
          <p className="diag-bar__path" title={bootPath}>
            로그: {bootPath}
          </p>
        )}
      </details>
    </div>
  );
}
