import { useCallback, useEffect, useState } from "react";
import { fetchDaemonHealth, type DaemonHealthPayload } from "../api/client";
import { useLocale } from "../i18n/useLocale";

type Props = {
  embedded?: boolean;
};

export function DaemonStatusBar({ embedded = false }: Props) {
  const { t } = useLocale();
  const [health, setHealth] = useState<DaemonHealthPayload | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    setError(null);
    void fetchDaemonHealth()
      .then(setHealth)
      .catch((err) => {
        setHealth(null);
        setError(err instanceof Error ? err.message : "unavailable");
      });
  }, []);

  useEffect(() => {
    load();
    const id = window.setInterval(load, 30_000);
    return () => window.clearInterval(id);
  }, [load]);

  const online = Boolean(health?.pid);
  const stale =
    health?.last_scheduler_tick_at &&
    Date.now() - new Date(health.last_scheduler_tick_at).getTime() > 180_000;

  const statusLabel = online
    ? stale
      ? t("missionOsDaemonStale")
      : t("missionOsDaemonOnline")
    : t("missionOsDaemonOffline");

  if (embedded) {
    return (
      <div className="settings-inline-row" data-settings-embedded>
        <span>{t("missionOsDaemon")}</span>
        <span
          className={`provider-status-row__state provider-status-row__state--${online && !stale ? "logged_in" : "error"}`}
        >
          {statusLabel}
        </span>
        {error ? <span className="settings-inline-note">{error}</span> : null}
      </div>
    );
  }

  return (
    <div className="mission-os-daemon">
      <div className="settings-section__sub-head">{t("missionOsDaemon")}</div>
      <dl className="settings-dl mission-os-daemon__dl">
        <div>
          <dt>{t("missionOsDaemonStatus")}</dt>
          <dd>
            <span
              className={`ctx-oracle-badge ctx-oracle-badge--${online && !stale ? "pass" : "warn"}`}
            >
              {online
                ? stale
                  ? t("missionOsDaemonStale")
                  : t("missionOsDaemonOnline")
                : t("missionOsDaemonOffline")}
            </span>
          </dd>
        </div>
        {health?.pid ? (
          <div>
            <dt>PID</dt>
            <dd>{health.pid}</dd>
          </div>
        ) : null}
        {health?.last_scheduler_tick_at ? (
          <div>
            <dt>{t("missionOsLastTick")}</dt>
            <dd>{health.last_scheduler_tick_at}</dd>
          </div>
        ) : null}
        {health?.scheduler_enabled != null ? (
          <div>
            <dt>{t("missionOsScheduler")}</dt>
            <dd>{health.scheduler_enabled ? "on" : "off"}</dd>
          </div>
        ) : null}
      </dl>
      {error ? (
        <p className="settings-hint settings-hint--error">{error}</p>
      ) : null}
      <button
        type="button"
        className="settings-btn settings-btn--ghost"
        onClick={load}
      >
        {t("refresh")}
      </button>
    </div>
  );
}
