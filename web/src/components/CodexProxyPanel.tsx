import { useEffect, useState } from "react";
import { fetchCodexProxyHealth, type CodexProxyHealth } from "../api/client";

type Props = {
  embedded?: boolean;
};

export function CodexProxyPanel({ embedded = false }: Props) {
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

  if (embedded && !envOn && !error) {
    return (
      <p
        className="settings-inline-note"
        data-settings-embedded
        data-testid="codex-proxy-panel"
      >
        Codex proxy off · CLI transport
      </p>
    );
  }

  return (
    <section
      className={`codex-proxy-panel${embedded ? " codex-proxy-panel--embedded" : ""}`}
      data-settings-embedded={embedded || undefined}
      data-testid="codex-proxy-panel"
    >
      {!embedded ? (
        <p className="codex-proxy-panel__hint">
          개발용 — <code>AGENT_LAB_CODEX_PROXY=1</code>
        </p>
      ) : null}
      {error ? <p className="codex-proxy-panel__error">{error}</p> : null}
      <div className="provider-status-row provider-status-row--flat">
        <span>Codex proxy</span>
        <span className="provider-status-row__state">
          {!envOn ? "off" : proxyOk ? "on" : "fail"}
        </span>
      </div>
      {envOn && status?.base_url ? (
        <p className="settings-inline-note">{status.base_url}</p>
      ) : null}
      {envOn && !proxyOk && status?.next ? (
        <p className="codex-proxy-panel__next">{status.next}</p>
      ) : null}
    </section>
  );
}
