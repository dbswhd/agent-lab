import { useCallback, useEffect, useRef, useState } from "react";
import { openUrl } from "@tauri-apps/plugin-opener";
import {
  authRunWsUrl,
  captureCodexAuthRun,
  type AuthRunRef,
} from "../api/client";
import { stripTerminalControlSequences } from "../utils/ttySanitize";

type Props = {
  run: AuthRunRef;
  onClose: () => void;
  onComplete: () => void;
};

type FlowStatus = "running" | "failed" | "cancelled";

const AUTH_CLI_SUCCESS_RE =
  /Login successful|Logout successful|Successfully logged out|✓ Logout successful|logged in using/i;

function authOutputLooksSuccessful(output: string): boolean {
  return AUTH_CLI_SUCCESS_RE.test(output);
}

export function AuthFlowPanel({ run, onClose, onComplete }: Props) {
  const [status, setStatus] = useState<FlowStatus>("running");
  const [errorOutput, setErrorOutput] = useState("");
  const [authUrl, setAuthUrl] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const flowLabel = run.action === "logout" ? "로그아웃" : "로그인";
  const wsRef = useRef<WebSocket | null>(null);
  const outputRef = useRef("");
  const onCloseRef = useRef(onClose);
  const onCompleteRef = useRef(onComplete);

  onCloseRef.current = onClose;
  onCompleteRef.current = onComplete;

  const finishSuccess = useCallback(async () => {
    if (run.provider_id === "codex" && run.action === "login") {
      try {
        await captureCodexAuthRun(run.id, "primary");
      } catch {
        /* live ~/.codex/auth.json is already updated after CLI login */
      }
    }
    onCompleteRef.current();
    onCloseRef.current();
  }, [run.action, run.id, run.provider_id]);

  const finishFailure = useCallback((next: FlowStatus, message?: string) => {
    setStatus(next);
    setErrorOutput(
      (message ?? outputRef.current).trim() ||
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

  const providerLabel =
    run.provider_id === "claude"
      ? "Claude"
      : run.provider_id === "codex"
        ? "Codex"
        : run.provider_id === "cursor"
          ? "Cursor"
          : run.provider_id;

  if (status !== "running") {
    return (
      <section
        className="auth-flow auth-flow--error"
        aria-label={`${providerLabel} ${flowLabel} 실패`}
      >
        <div className="auth-flow__head">
          <strong>
            {providerLabel} {flowLabel} 실패
          </strong>
          <span className={`auth-flow__status auth-flow__status--${status}`}>
            {status === "cancelled" ? "취소됨" : "실패"}
          </span>
        </div>
        <pre className="auth-flow__output" aria-live="polite">
          {errorOutput}
        </pre>
        <div className="auth-flow__input-row">
          <button type="button" className="btn btn--sm" onClick={onClose}>
            닫기
          </button>
        </div>
      </section>
    );
  }

  return (
    <section
      className="auth-flow auth-flow--running"
      aria-label={`${providerLabel} ${flowLabel}`}
    >
      <div className="auth-flow__head">
        <strong>
          {providerLabel} {flowLabel}
        </strong>
        <span className="auth-flow__status">진행 중</span>
      </div>
      <p className="auth-flow__hint">
        {run.action === "logout"
          ? "CLI 로그아웃을 실행 중입니다."
          : run.provider_id === "claude"
            ? "브라우저에서 승인한 뒤, 코드가 표시되면 아래에 붙여넣으세요."
            : "브라우저에서 승인하면 자동으로 완료됩니다."}
      </p>
      {authUrl ? (
        <button
          type="button"
          className="btn btn--sm"
          onClick={() => void openUrl(authUrl).catch(() => undefined)}
        >
          브라우저에서 계속
        </button>
      ) : null}
      <div className="auth-flow__input-row">
        {run.action === "login" ? (
          <>
            <input
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") submitInput();
              }}
              placeholder="인증 코드 (필요할 때만)"
              aria-label="인증 코드 입력"
            />
            <button type="button" className="btn btn--sm" onClick={submitInput}>
              입력
            </button>
          </>
        ) : null}
        <button
          type="button"
          className="btn btn--danger btn--sm"
          onClick={() =>
            wsRef.current?.send(JSON.stringify({ type: "cancel" }))
          }
        >
          취소
        </button>
      </div>
    </section>
  );
}
