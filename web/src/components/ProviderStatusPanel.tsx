import { useCallback, useEffect, useState } from "react";
import { fetchProviderAuth, type ProviderAuthRow } from "../api/client";
import { Avatar } from "./Avatar";
import type { AgentRole } from "../utils/transcript";

const STATUS_LABELS = {
  logged_in: "연결됨",
  logged_out: "로그인 필요",
  unavailable: "CLI 없음",
  checking: "확인 중",
  error: "확인 실패",
} as const;

function compactMask(value: string): string {
  return value.length > 16 ? `••••••••${value.slice(-4)}` : value;
}

type Props = {
  /** Settings shell — flat rows, no intro hint. */
  embedded?: boolean;
};

export function ProviderStatusPanel({ embedded = false }: Props) {
  const [providers, setProviders] = useState<ProviderAuthRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const response = await fetchProviderAuth();
      setProviders(response.providers);
      setError(null);
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "상태를 불러오지 못했습니다.",
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
    const timer = window.setInterval(() => void load(), 3000);
    return () => window.clearInterval(timer);
  }, [load]);

  if (error && providers.length === 0) {
    return <p className="settings-hint">{error}</p>;
  }

  return (
    <div
      className="settings-credentials"
      data-settings-embedded={embedded || undefined}
      data-testid="provider-status-panel"
    >
      {!embedded ? (
        <p className="settings-hint">
          변경은 Transcript <code>/login</code> · <code>/logout</code>
        </p>
      ) : null}
      <div className="provider-status-list">
        {loading ? <p className="settings-hint">확인 중…</p> : null}
        {providers.map((provider) => {
          const credential = provider.accounts;
          const accountLine = credential?.primary_masked
            ? compactMask(credential.primary_masked)
            : provider.account_mode === "ambient"
              ? "CLI"
              : null;
          return (
            <div className="provider-status-row" key={provider.id}>
              <Avatar
                role={provider.id as AgentRole}
                label={provider.label}
                size={20}
              />
              <div className="provider-status-row__body">
                <strong>{provider.label}</strong>
                {!embedded && accountLine ? (
                  <span className="provider-status-row__meta">
                    {accountLine}
                  </span>
                ) : null}
              </div>
              <span
                className={`provider-status-row__state provider-status-row__state--${provider.state}`}
                title={provider.detail ?? undefined}
              >
                {STATUS_LABELS[provider.state]}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
