import { useEffect, useState } from "react";
import { fetchCodexProxyHealth, type CodexProxyHealth } from "../api/client";

export function CodexProxyPanel() {
  const [status, setStatus] = useState<CodexProxyHealth | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void fetchCodexProxyHealth()
      .then((payload) => {
        if (!cancelled) setStatus(payload);
      })
      .catch((e: unknown) => {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : String(e));
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const envOn = Boolean(status?.env_enabled);
  const proxyOk = Boolean(status?.ok);

  return (
    <section className="codex-proxy-panel" data-testid="codex-proxy-panel">
      <p className="codex-proxy-panel__hint">
        개발용 Codex transport — <code>AGENT_LAB_CODEX_PROXY=1</code> +{" "}
        <code>npx openai-oauth</code>. MCP/inbox execute 경로는 CLI를 사용합니다.
      </p>
      {error ? <p className="codex-proxy-panel__error">{error}</p> : null}
      <dl className="codex-proxy-panel__rows">
        <div>
          <dt>환경</dt>
          <dd>{envOn ? "proxy on" : "proxy off (CLI)"}</dd>
        </div>
        <div>
          <dt>엔드포인트</dt>
          <dd>{status?.base_url ?? "—"}</dd>
        </div>
        <div>
          <dt>상태</dt>
          <dd>
            {!envOn
              ? "비활성"
              : proxyOk
                ? status?.detail ?? "reachable"
                : status?.detail ?? "unreachable"}
          </dd>
        </div>
      </dl>
      {envOn && !proxyOk && status?.next ? (
        <p className="codex-proxy-panel__next">{status.next}</p>
      ) : null}
    </section>
  );
}
