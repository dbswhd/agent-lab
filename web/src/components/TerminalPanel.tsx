import { useEffect, useRef, useState } from "react";
import { Terminal } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";
import "@xterm/xterm/css/xterm.css";
import { terminalWsUrl } from "../api/client";
import { useLocale } from "../i18n/useLocale";

type Props = { sessionId: string };

type Status = "idle" | "connecting" | "connected" | "exited" | "error";

export function TerminalPanel({ sessionId }: Props) {
  const { msg } = useLocale();
  const [status, setStatus] = useState<Status>("idle");
  const wsRef = useRef<WebSocket | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const termRef = useRef<Terminal | null>(null);
  const fitRef = useRef<FitAddon | null>(null);

  function sendResize() {
    const term = termRef.current;
    const ws = wsRef.current;
    if (!term || ws?.readyState !== WebSocket.OPEN) return;
    ws.send(
      JSON.stringify({ type: "resize", rows: term.rows, cols: term.cols }),
    );
  }

  function disposeTerminal() {
    termRef.current?.dispose();
    termRef.current = null;
    fitRef.current = null;
  }

  function connect() {
    if (wsRef.current || !containerRef.current) return;
    setStatus("connecting");

    const term = new Terminal({
      cursorBlink: true,
      fontSize: 13,
      fontFamily:
        "var(--font-mono, ui-monospace, SFMono-Regular, Menlo, monospace)",
      theme: {
        background: "#1a1b1e",
        foreground: "#e8e8ea",
        cursor: "#7aa2ff",
      },
      scrollback: 5000,
    });
    const fitAddon = new FitAddon();
    term.loadAddon(fitAddon);
    term.open(containerRef.current);
    fitAddon.fit();
    termRef.current = term;
    fitRef.current = fitAddon;
    sendResize();

    const ws = new WebSocket(terminalWsUrl(sessionId));
    wsRef.current = ws;

    term.onData((data) => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: "input", data }));
      }
    });

    ws.onopen = () => {
      setStatus("connected");
      fitAddon.fit();
      sendResize();
      term.focus();
    };

    ws.onmessage = (e) => {
      let payload: { type: string; data?: string };
      try {
        payload = JSON.parse(e.data as string) as typeof payload;
      } catch {
        return;
      }
      if (payload.type === "output" && payload.data) {
        term.write(payload.data);
      } else if (payload.type === "exit") {
        setStatus("exited");
        wsRef.current = null;
      }
    };

    ws.onclose = () => {
      setStatus((prev) => (prev === "exited" ? "exited" : "idle"));
      wsRef.current = null;
    };

    ws.onerror = () => {
      setStatus("error");
      wsRef.current = null;
    };
  }

  function disconnect() {
    wsRef.current?.close();
    wsRef.current = null;
    disposeTerminal();
    setStatus("idle");
  }

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const ro = new ResizeObserver(() => {
      fitRef.current?.fit();
      sendResize();
    });
    ro.observe(container);
    return () => ro.disconnect();
  }, [status]);

  useEffect(() => {
    return () => {
      wsRef.current?.close();
      wsRef.current = null;
      disposeTerminal();
    };
  }, []);

  const isConnected = status === "connected";

  return (
    <div className="terminal-panel terminal-panel--xterm">
      <div className="terminal-panel__toolbar">
        <svg
          viewBox="0 0 24 24"
          width={14}
          height={14}
          fill="none"
          stroke="currentColor"
          strokeWidth={1.7}
          strokeLinecap="round"
          aria-hidden
        >
          <polyline points="4 17 10 11 4 5" />
          <line x1="12" y1="19" x2="20" y2="19" />
        </svg>
        <span className="terminal-panel__title">{msg.terminal}</span>
        <span
          className={`terminal-panel__status terminal-panel__status--${status}`}
        >
          {status === "idle"
            ? msg.terminalOffline
            : status === "connecting"
              ? msg.terminalConnecting
              : status === "connected"
                ? msg.terminalConnected
                : status === "exited"
                  ? msg.terminalExited
                  : msg.terminalError}
        </span>
        <div className="terminal-panel__toolbar-actions">
          {isConnected ? (
            <>
              <button
                type="button"
                className="btn btn--sm btn--ghost"
                onClick={() => termRef.current?.clear()}
              >
                {msg.terminalClear}
              </button>
              <button
                type="button"
                className="btn btn--sm btn--ghost"
                onClick={disconnect}
              >
                {msg.terminalDisconnect}
              </button>
            </>
          ) : (
            <button
              type="button"
              className="btn btn--sm"
              onClick={connect}
              disabled={status === "connecting"}
            >
              {msg.terminalConnect}
            </button>
          )}
        </div>
      </div>

      <div
        ref={containerRef}
        className="terminal-panel__xterm"
        onClick={() => termRef.current?.focus()}
        role="application"
        aria-label={msg.terminal}
      />
      {!isConnected && status === "idle" ? (
        <div className="terminal-panel__hint">{msg.terminalHint}</div>
      ) : null}
    </div>
  );
}
