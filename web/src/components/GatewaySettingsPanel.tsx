import { useCallback, useEffect, useState } from "react";
import {
  fetchGatewaySettings,
  patchGatewaySettings,
  pingGateway,
  type GatewaySettingsPayload,
} from "../api/client";
import { useLocale } from "../i18n/useLocale";
import { SettingsSectionIcon } from "./SettingsSectionIcon";

export function GatewaySettingsPanel() {
  const { t } = useLocale();
  const [settings, setSettings] = useState<GatewaySettingsPayload | null>(null);
  const [outboundUrls, setOutboundUrls] = useState("");
  const [hybridUrl, setHybridUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [hint, setHint] = useState<string | null>(null);

  const load = useCallback(() => {
    void fetchGatewaySettings().then((payload) => {
      setSettings(payload);
      setOutboundUrls((payload.outbound?.urls ?? []).join("\n"));
      setHybridUrl(payload.hybrid?.relay_url ?? "");
    });
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const save = async () => {
    setBusy(true);
    setHint(null);
    try {
      const urls = outboundUrls
        .split("\n")
        .map((u) => u.trim())
        .filter(Boolean);
      const res = await patchGatewaySettings({
        outbound: { enabled: true, urls },
        hybrid: { enabled: Boolean(hybridUrl.trim()), relay_url: hybridUrl.trim() || null },
      });
      setSettings(res);
      setHint(t("saved"));
    } catch (err) {
      setHint(err instanceof Error ? err.message : "save failed");
    } finally {
      setBusy(false);
    }
  };

  const ping = async () => {
    setBusy(true);
    setHint(null);
    try {
      const res = await pingGateway();
      setHint(res.ok ? t("missionOsPingOk") : t("missionOsPingFail"));
    } catch (err) {
      setHint(err instanceof Error ? err.message : "ping failed");
    } finally {
      setBusy(false);
    }
  };

  const adapters = settings?.adapters ?? [];

  return (
    <div className="mission-os-gateway">
      <div className="settings-section__sub-head">
        <SettingsSectionIcon name="activity" />
        {t("missionOsGateway")}
      </div>
      <label className="settings-field">
        <span>{t("missionOsOutboundUrls")}</span>
        <textarea
          className="settings-textarea"
          rows={3}
          value={outboundUrls}
          onChange={(e) => setOutboundUrls(e.target.value)}
          placeholder="https://example.com/hook"
        />
      </label>
      <label className="settings-field">
        <span>{t("missionOsHybridRelay")}</span>
        <input
          className="settings-input"
          value={hybridUrl}
          onChange={(e) => setHybridUrl(e.target.value)}
          placeholder="https://worker.example/relay"
        />
      </label>
      <div className="settings-actions">
        <button type="button" className="settings-btn" disabled={busy} onClick={() => void save()}>
          {t("save")}
        </button>
        <button type="button" className="settings-btn settings-btn--ghost" disabled={busy} onClick={() => void ping()}>
          {t("missionOsPing")}
        </button>
      </div>
      {hint ? <p className="settings-hint">{hint}</p> : null}
      {adapters.length > 0 ? (
        <>
          <div className="settings-section__sub-head">{t("missionOsAdapters")}</div>
          <ul className="mission-os-adapters">
            {adapters.map((row) => (
              <li key={row.id}>
                <code>{row.id}</code>
                <span className={row.enabled ? "is-on" : "is-off"}>
                  {row.enabled ? "enabled" : "disabled"}
                </span>
                {row.description ? <small>{row.description}</small> : null}
              </li>
            ))}
          </ul>
        </>
      ) : null}
    </div>
  );
}
