import { useCallback, useEffect, useState } from "react";
import type { DiagnosticsResponse } from "../api/client";
import { fetchDiagnostics } from "../api/client";

type Props = {
  apiOk: boolean;
  sessionsDir: string | null;
  probeBridgeFailed: boolean;
};

export function ApiDiagnosticsBar({
  apiOk,
  sessionsDir,
  probeBridgeFailed,
}: Props) {
  const [diag, setDiag] = useState<DiagnosticsResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [copied, setCopied] = useState(false);

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
    if (apiOk) {
      void load();
      return;
    }
    void load();
    const id = window.setInterval(() => void load(), 8_000);
    return () => window.clearInterval(id);
  }, [apiOk, load]);

  async function copyJson() {
    if (!diag) return;
    try {
      await navigator.clipboard.writeText(JSON.stringify(diag, null, 2));
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      /* ignore */
    }
  }

  const bootPath = diag?.boot_log_path ?? "~/Library/Logs/Agent Lab/agent-lab-boot.log";
  const displaySessions = sessionsDir ?? diag?.sessions_dir ?? null;

  return (
    <div className="api-diagnostics-bar" aria-label="API diagnostics">
      {displaySessions ? (
        <p className="api-diagnostics-bar__sessions" title={displaySessions}>
          세션: {displaySessions}
        </p>
      ) : null}
      {!apiOk ? (
        <p className="api-diagnostics-bar__offline">
          API 연결 끊김 — <code>make dev</code> 또는 앱 재시작 후 ↻ 새로고침
        </p>
      ) : null}
      {probeBridgeFailed ? (
        <p className="api-diagnostics-bar__hint">
          Cursor bridge 실패 — <code>~/.agent-lab/.env</code>에{" "}
          <code>CURSOR_SDK_BRIDGE_BIN</code> 절대 경로 설정.{" "}
          <code>docs/STABILITY.md</code> 참고.
        </p>
      ) : null}
      <div className="api-diagnostics-bar__actions">
        <button
          type="button"
          className="mac-btn-secondary mac-btn-secondary--compact"
          disabled={loading}
          onClick={() => void load()}
        >
          {loading ? "…" : "진단 새로고침"}
        </button>
        <button
          type="button"
          className="mac-btn-secondary mac-btn-secondary--compact"
          disabled={!diag}
          onClick={() => void copyJson()}
        >
          {copied ? "복사됨" : "진단 JSON 복사"}
        </button>
      </div>
      {diag?.boot_log_tail?.length ? (
        <details className="api-diagnostics-bar__boot">
          <summary>부트 로그 (최근 {diag.boot_log_tail.length}줄)</summary>
          <p className="api-diagnostics-bar__path" title={bootPath}>
            {bootPath}
          </p>
          <pre className="api-diagnostics-bar__log">
            {diag.boot_log_tail.join("\n")}
          </pre>
        </details>
      ) : (
        <p className="api-diagnostics-bar__path" title={bootPath}>
          로그: {bootPath}
        </p>
      )}
    </div>
  );
}
