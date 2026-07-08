import { useCallback, useEffect, useRef, useState } from "react";
import { openUrl } from "@tauri-apps/plugin-opener";
import {
  authRunWsUrl,
  captureCodexAuthRun,
  type AuthRunRef,
} from "../api/client";
import { useDismissOnPointerDownOutside } from "../hooks/useDismissOnPointerDownOutside";
import { stripTerminalControlSequences } from "../utils/ttySanitize";

type Props = {
  run: AuthRunRef;
  onClose: () => void;
  onComplete: () => void | Promise<void>;
};

type FlowStatus = "running" | "failed" | "cancelled";

const AUTH_CLI_SUCCESS_RE =
  /Login successful|Logout successful|Successfully logged out|✓ Logout successful|logged in using/i;

const BROWSER_OAUTH_PROVIDERS = new Set(["claude", "codex", "cursor"]);

function authOutputLooksSuccessful(output: string): boolean {
  return AUTH_CLI_SUCCESS_RE.test(output);
}

function humanizeClaudeAuthStatusOutput(output: string): string {
  const trimmed = output.trim();
  if (!trimmed.includes('"loggedIn"')) return output;
  try {
    const payload = JSON.parse(trimmed) as {
      loggedIn?: boolean;
      email?: string;
    };
    if (payload.loggedIn) {
      return payload.email ? `OAuth 연결됨 (${payload.email})` : "OAuth 연결됨";
    }
    return "OAuth 미로그인 — /login 또는 claude auth login";
  } catch {
    return output;
  }
}

function formatAuthFailureOutput(output: string): string {
  const lines = output
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
  if (lines.length === 0) return output;
  const normalized = lines.map((line) =>
    line.startsWith("{") && line.includes('"loggedIn"')
      ? humanizeClaudeAuthStatusOutput(line)
      : line,
  );
  return normalized.join("\n");
}

function providerLabel(providerId: string): string {
  if (providerId === "claude") return "Claude";
  if (providerId === "codex") return "Codex";
  if (providerId === "cursor") return "Cursor";
  return providerId;
}

/** OAuth CLI progress — anchored above composer (replaces bottom AuthFlowPanel). */
export function ComposerAuthFlowPopover({ run, onClose, onComplete }: Props) {
  const [status, setStatus] = useState<FlowStatus>("running");
  const [errorOutput, setErrorOutput] = useState("");
  const [authUrl, setAuthUrl] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const flowLabel = run.action === "logout" ? "로그아웃" : "로그인";
  const wsRef = useRef<WebSocket | null>(null);
  const outputRef = useRef("");
  const onCloseRef = useRef(onClose);
  const onCompleteRef = useRef(onComplete);
  const handleDismiss = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: "cancel" }));
    }
    onClose();
  }, [onClose]);

  const popoverRef = useDismissOnPointerDownOutside(true, handleDismiss);

  onCloseRef.current = onClose;
  onCompleteRef.current = onComplete;

  const finishSuccess = useCallback(async () => {
    if (run.provider_id === "codex" && run.action === "login") {
      try {
        await captureCodexAuthRun(run.id, "primary", true);
      } catch {
        /* capture failed — the fresh login stays live; the freshness guard in
           apply_profile prevents the stale snapshot from stomping it */
      }
    }
    await onCompleteRef.current();
    onCloseRef.current();
  }, [run.action, run.id, run.provider_id]);

  const finishFailure = useCallback((next: FlowStatus, message?: string) => {
    setStatus(next);
    const raw = (message ?? outputRef.current).trim();
    setErrorOutput(
      formatAuthFailureOutput(raw) ||
        "인증 연결이 끊어졌습니다. CLI 출력을 확인하세요.",
    );
  }, []);

  useEffect(() => {
    const ws = new WebSocket(authRunWsUrl(run.id));
    wsRef.current = ws;
    outputRef.current = "";
    let disposed = false;
    let terminal = false;

    const markCompleted = () => {
      if (terminal) return;
      terminal = true;
      void finishSuccess();
    };

    ws.onmessage = (message) => {
      let event: {
        type: string;
        data?: string;
        url?: string;
        detail?: string;
      };
      try {
        event = JSON.parse(message.data as string) as typeof event;
      } catch {
        return;
      }
      if (event.type === "output" && event.data) {
        const chunk = stripTerminalControlSequences(event.data);
        if (!chunk) return;
        outputRef.current = `${outputRef.current}${chunk}`.slice(-8000);
      } else if (event.type === "auth_url" && event.url) {
        setAuthUrl(event.url);
        void openUrl(event.url).catch(() => undefined);
      } else if (event.type === "completed") {
        if (event.detail) {
          outputRef.current = `${outputRef.current}\n${event.detail}`.slice(
            -8000,
          );
        }
        markCompleted();
        ws.close(1000);
      } else if (event.type === "failed" || event.type === "cancelled") {
        if (event.detail) {
          outputRef.current = `${outputRef.current}\n${event.detail}`.slice(
            -8000,
          );
        }
        terminal = true;
        finishFailure(
          event.type,
          outputRef.current || event.detail || undefined,
        );
        ws.close(1000);
      }
    };
    ws.onclose = () => {
      if (disposed || terminal) return;
      if (authOutputLooksSuccessful(outputRef.current)) {
        markCompleted();
        return;
      }
      finishFailure("failed");
    };
    return () => {
      disposed = true;
      ws.close();
      wsRef.current = null;
    };
  }, [finishFailure, finishSuccess, run.id]);

  const submitInput = () => {
    if (!input || wsRef.current?.readyState !== WebSocket.OPEN) return;
    wsRef.current.send(JSON.stringify({ type: "input", data: `${input}\n` }));
    setInput("");
  };

  const label = providerLabel(run.provider_id);
  const browserOAuthLogin =
    run.action === "login" && BROWSER_OAUTH_PROVIDERS.has(run.provider_id);

  return (
    <div
      ref={popoverRef}
      className="slash-command-menu composer-auth-flow-popover"
      role="dialog"
      aria-label={`${label} ${flowLabel}`}
      data-testid="composer-auth-flow-popover"
    >
      <div className="slash-command-menu__main">
        <div className="composer-auth-flow-popover__head">
          <strong>
            {label} {flowLabel}
          </strong>
          <span
            className={[
              "composer-auth-flow-popover__status",
              status !== "running" ? "is-error" : "",
            ]
              .filter(Boolean)
              .join(" ")}
          >
            {status === "running"
              ? "진행 중"
              : status === "cancelled"
                ? "취소됨"
                : "실패"}
          </span>
        </div>
        {status === "running" ? (
          <p className="composer-auth-flow-popover__hint">
            {run.action === "logout"
              ? "CLI 로그아웃을 실행 중입니다."
              : browserOAuthLogin
                ? "브라우저에서 승인하면 자동으로 완료됩니다."
                : "브라우저에서 승인한 뒤, 코드가 표시되면 아래에 붙여넣으세요."}
          </p>
        ) : (
          <pre
            className="composer-auth-flow-popover__output"
            aria-live="polite"
          >
            {errorOutput}
          </pre>
        )}
        <div className="composer-auth-flow-popover__actions">
          {status === "running" && authUrl ? (
            <button
              type="button"
              className="composer-slash-choice__action"
              onClick={() => void openUrl(authUrl).catch(() => undefined)}
            >
              브라우저에서 계속
            </button>
          ) : null}
          {status === "running" &&
          run.action === "login" &&
          !browserOAuthLogin ? (
            <>
              <input
                className="composer-auth-flow-popover__input"
                value={input}
                onChange={(event) => setInput(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") submitInput();
                }}
                placeholder="인증 코드 (필요할 때만)"
                aria-label="인증 코드 입력"
              />
              <button
                type="button"
                className="composer-slash-choice__action"
                onClick={submitInput}
              >
                입력
              </button>
            </>
          ) : null}
          <button
            type="button"
            className={[
              "composer-slash-choice__action",
              status === "running"
                ? "composer-slash-choice__action--danger"
                : "",
            ]
              .filter(Boolean)
              .join(" ")}
            onClick={() => {
              if (status === "running") {
                wsRef.current?.send(JSON.stringify({ type: "cancel" }));
                return;
              }
              onClose();
            }}
          >
            {status === "running" ? "취소" : "닫기"}
          </button>
        </div>
      </div>
    </div>
  );
}
