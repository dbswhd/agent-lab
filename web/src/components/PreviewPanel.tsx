import { useCallback, useEffect, useRef, useState } from "react";
import {
  clearPreviewPort,
  getPreviewPresets,
  getPreviewStatus,
  probePreviewPort,
  setPreviewPort,
  submitBgTask,
  type DevServerPreset,
  type PreviewStatus,
} from "../api/client";
import { useLocale } from "../i18n/useLocale";

type Props = {
  sessionId: string;
};

export function PreviewPanel({ sessionId }: Props) {
  const { msg } = useLocale();
  const [status, setStatus] = useState<PreviewStatus>({
    port: null,
    alive: false,
  });
  const [inputPort, setInputPort] = useState("");
  const [saving, setSaving] = useState(false);
  const [probing, setProbing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [presets, setPresets] = useState<DevServerPreset[]>([]);
  const [startingPreset, setStartingPreset] = useState<string | null>(null);
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const autoProbedRef = useRef(false);

  const applyStatus = useCallback((s: PreviewStatus) => {
    setStatus(s);
    if (s.port) setInputPort(String(s.port));
  }, []);

  useEffect(() => {
    getPreviewStatus(sessionId)
      .then(applyStatus)
      .catch(() => {});
    getPreviewPresets(sessionId)
      .then((res) => setPresets(res.presets ?? []))
      .catch(() => {});
  }, [sessionId, applyStatus]);

  const runProbe = useCallback(async () => {
    setError(null);
    setProbing(true);
    try {
      const result = await probePreviewPort(sessionId);
      applyStatus(result);
      if (!result.port) {
        setError(msg.previewProbeNone);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : msg.previewConnectFailed);
    } finally {
      setProbing(false);
    }
  }, [sessionId, applyStatus, msg]);

  useEffect(() => {
    if (autoProbedRef.current || status.port) return;
    autoProbedRef.current = true;
    void runProbe();
  }, [status.port, runProbe]);

  const connect = useCallback(async () => {
    const port = parseInt(inputPort, 10);
    if (isNaN(port)) {
      setError(msg.previewInvalidPort);
      return;
    }
    setError(null);
    setSaving(true);
    try {
      const s = await setPreviewPort(sessionId, port);
      applyStatus(s);
    } catch (e) {
      let errMsg = e instanceof Error ? e.message : msg.previewConnectFailed;
      try {
        const parsed = JSON.parse(errMsg) as { detail?: string };
        if (parsed.detail) errMsg = parsed.detail;
      } catch {
        /* not JSON */
      }
      setError(errMsg);
    } finally {
      setSaving(false);
    }
  }, [sessionId, inputPort, msg, applyStatus]);

  const disconnect = useCallback(async () => {
    await clearPreviewPort(sessionId);
    setStatus({ port: null, alive: false });
    setInputPort("");
    setError(null);
  }, [sessionId]);

  const refresh = useCallback(() => {
    iframeRef.current?.contentWindow?.location.reload();
  }, []);

  const startPreset = useCallback(
    async (preset: DevServerPreset) => {
      setStartingPreset(preset.id);
      setError(null);
      try {
        await submitBgTask(sessionId, preset.label, preset.command, preset.cwd);
        for (let i = 0; i < 15; i += 1) {
          await new Promise((r) => setTimeout(r, 2000));
          const result = await probePreviewPort(sessionId);
          if (result.port && result.alive) {
            applyStatus(result);
            return;
          }
        }
        setError(msg.previewProbeNone);
      } catch (e) {
        setError(e instanceof Error ? e.message : msg.previewConnectFailed);
      } finally {
        setStartingPreset(null);
      }
    },
    [sessionId, applyStatus, msg],
  );

  const iframeSrc = status.port ? `http://localhost:${status.port}/` : null;

  return (
    <div className="preview-panel">
      <div className="preview-panel__toolbar">
        <span
          className={`dot ${status.alive ? "dot--live" : "dot--idle"}`}
          aria-hidden
        />
        <input
          className="preview-panel__port-input"
          type="number"
          min={1024}
          max={65534}
          placeholder="포트 (예: 3000)"
          value={inputPort}
          onChange={(e) => setInputPort(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && void connect()}
          aria-label="Dev server port"
        />
        <button
          type="button"
          className="btn btn--sm"
          onClick={() => void connect()}
          disabled={saving || !inputPort}
        >
          {saving ? msg.previewConnecting : msg.previewConnect}
        </button>
        <button
          type="button"
          className="btn btn--sm btn--ghost"
          onClick={() => void runProbe()}
          disabled={probing}
          title={msg.previewAutoDetect}
        >
          {probing ? msg.previewProbing : msg.previewAutoDetect}
        </button>
        {status.port ? (
          <>
            <button
              type="button"
              className="btn btn--sm btn--ghost"
              onClick={refresh}
              title={msg.previewRefresh}
              aria-label={msg.previewRefresh}
            >
              <RefreshIcon />
            </button>
            <button
              type="button"
              className="btn btn--sm btn--ghost"
              onClick={() => void disconnect()}
              title={msg.previewDisconnect}
              aria-label={msg.previewDisconnect}
            >
              <CloseIcon />
            </button>
          </>
        ) : null}
        {error ? <span className="preview-panel__error">{error}</span> : null}
      </div>

      {presets.length > 0 ? (
        <div className="preview-panel__presets">
          {presets.map((preset) => (
            <button
              key={preset.id}
              type="button"
              className="btn btn--sm btn--ghost preview-panel__preset"
              disabled={startingPreset != null}
              onClick={() => void startPreset(preset)}
            >
              {startingPreset === preset.id
                ? msg.previewStarting
                : preset.label}
            </button>
          ))}
        </div>
      ) : null}

      {iframeSrc ? (
        <iframe
          ref={iframeRef}
          src={iframeSrc}
          className="preview-panel__iframe"
          title="Dev server preview"
          sandbox="allow-scripts allow-same-origin allow-forms allow-popups"
        />
      ) : (
        <div className="empty-state">
          <span className="empty-state__icon" aria-hidden>
            <MonitorIcon />
          </span>
          <span className="empty-state__title">{msg.previewEmptyTitle}</span>
          <span className="empty-state__hint">{msg.previewEmptyHint}</span>
        </div>
      )}
    </div>
  );
}

function RefreshIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      width={13}
      height={13}
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8" />
      <path d="M21 3v5h-5" />
      <path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16" />
      <path d="M8 16H3v5" />
    </svg>
  );
}

function CloseIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      width={13}
      height={13}
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      aria-hidden
    >
      <path d="M18 6 6 18M6 6l12 12" />
    </svg>
  );
}

function MonitorIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      width={24}
      height={24}
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <rect x="2" y="3" width="20" height="14" rx="2" />
      <path d="M8 21h8M12 17v4" />
    </svg>
  );
}
