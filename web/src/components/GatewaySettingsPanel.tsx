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
  const [slackEnabled, setSlackEnabled] = useState(false);
  const [slackWebhook, setSlackWebhook] = useState("");
  const [slackBotToken, setSlackBotToken] = useState("");
  const [slackSigningSecret, setSlackSigningSecret] = useState("");
  const [slackChannels, setSlackChannels] = useState("");
  const [busy, setBusy] = useState(false);
  const [hint, setHint] = useState<string | null>(null);

  const load = useCallback(() => {
    void fetchGatewaySettings().then((payload) => {
      setSettings(payload);
      setOutboundUrls((payload.outbound?.urls ?? []).join("\n"));
      setHybridUrl(payload.hybrid?.relay_url ?? "");
      setSlackEnabled(Boolean(payload.slack?.enabled));
      setSlackChannels((payload.slack?.allowed_channel_ids ?? []).join(", "));
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
      const channels = slackChannels
        .split(",")
        .map((c) => c.trim())
        .filter(Boolean);
      const slackPatch: Record<string, unknown> = {
        enabled: slackEnabled,
        allowed_channel_ids: channels,
        allow_ingress_without_webhook: true,
      };
      if (slackWebhook.trim()) slackPatch.webhook_url = slackWebhook.trim();
      if (slackBotToken.trim()) slackPatch.bot_token = slackBotToken.trim();
      if (slackSigningSecret.trim()) slackPatch.signing_secret = slackSigningSecret.trim();

      const res = await patchGatewaySettings({
        outbound: { enabled: true, urls },
        hybrid: { enabled: Boolean(hybridUrl.trim()), relay_url: hybridUrl.trim() || null },
        slack: slackPatch,
      });
      setSettings(res);
      setSlackBotToken("");
      setSlackSigningSecret("");
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
  const slack = settings?.slack;

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

      <div className="settings-section__sub-head">{t("missionOsSlack")}</div>
      <label className="settings-field settings-field--row">
        <span>{t("missionOsSlackEnabled")}</span>
        <input
          type="checkbox"
          checked={slackEnabled}
          onChange={(e) => setSlackEnabled(e.target.checked)}
        />
      </label>
      <label className="settings-field">
        <span>{t("missionOsSlackWebhook")}</span>
        <input
          className="settings-input"
          value={slackWebhook}
          onChange={(e) => setSlackWebhook(e.target.value)}
          placeholder={
            slack?.webhook_url_set ? t("missionOsSecretPlaceholder") : "https://hooks.slack.com/..."
          }
        />
      </label>
      <label className="settings-field">
        <span>{t("missionOsSlackBotToken")}</span>
        <input
          className="settings-input"
          type="password"
          autoComplete="off"
          value={slackBotToken}
          onChange={(e) => setSlackBotToken(e.target.value)}
          placeholder={slack?.bot_token_set ? t("missionOsSecretPlaceholder") : "xoxb-..."}
        />
      </label>
      <label className="settings-field">
        <span>{t("missionOsSlackSigningSecret")}</span>
        <input
          className="settings-input"
          type="password"
          autoComplete="off"
          value={slackSigningSecret}
          onChange={(e) => setSlackSigningSecret(e.target.value)}
          placeholder={slack?.signing_secret_set ? t("missionOsSecretPlaceholder") : ""}
        />
      </label>
      <label className="settings-field">
        <span>{t("missionOsSlackChannels")}</span>
        <input
          className="settings-input"
          value={slackChannels}
          onChange={(e) => setSlackChannels(e.target.value)}
          placeholder="C01234567, C89ABCDEF"
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
