import { useEffect, useRef, useState } from "react";
import { openUrl } from "@tauri-apps/plugin-opener";
import {
  authRunWsUrl,
  captureCodexAuthRun,
  fetchProviderAuth,
  type AuthRunRef,
} from "../api/client";

type Props = {
  run: AuthRunRef;
  onClose: () => void;
  onComplete: () => void;
};

type FlowStatus = "running" | "completed" | "failed" | "cancelled";

const STATUS_LABELS: Record<FlowStatus, string> = {
  running: "진행 중",
  completed: "완료",
  failed: "실패",
  cancelled: "취소됨",
};

export function AuthFlowPanel({ run, onClose, onComplete }: Props) {
  const [status, setStatus] = useState<FlowStatus>("running");
  const [output, setOutput] = useState("");
  const [authUrl, setAuthUrl] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const [captureHint, setCaptureHint] = useState<string | null>(null);
  const flowLabel = run.action === "logout" ? "로그아웃" : "로그인";
  const [codexSlots, setCodexSlots] = useState<{
    hasPrimary: boolean;
    hasFallback: boolean;
  } | null>(null);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    const wsUrl = authRunWsUrl(run.id);
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;
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
        setOutput((current) => `${current}${event.data}`.slice(-8000));
      } else if (event.type === "auth_url" && event.url) {
        setAuthUrl(event.url);
        void openUrl(event.url).catch(() => undefined);
      } else if (
        event.type === "completed" ||
        event.type === "failed" ||
        event.type === "cancelled"
      ) {
        setStatus(event.type);
        if (event.detail) setOutput((current) => `${current}\n${event.detail}`);
        if (event.type === "completed") {
          onComplete();
          if (run.provider_id === "codex") {
            void fetchProviderAuth()
              .then((payload) => {
                const codex = payload.providers.find(
                  (provider) => provider.id === "codex",
                );
                setCodexSlots({
                  hasPrimary: codex?.profiles?.has_primary ?? false,
                  hasFallback: codex?.profiles?.has_fallback ?? false,
                });
              })
              .catch(() => undefined);
          }
        }
        ws.close(1000);
      }
    };
    ws.onerror = () => {
      setStatus((current) => (current === "running" ? "failed" : current));
      setOutput((current) => current || `인증 연결 실패: ${wsUrl}`);
    };
    return () => {
      ws.close();
      wsRef.current = null;
    };
  }, [onComplete, run.id, run.provider_id]);

  const submitInput = () => {
    if (!input || wsRef.current?.readyState !== WebSocket.OPEN) return;
    wsRef.current.send(JSON.stringify({ type: "input", data: `${input}\n` }));
    setInput("");
  };

  const capture = async (slot: "primary" | "fallback") => {
    try {
      await captureCodexAuthRun(run.id, slot);
      setCaptureHint(`${slot === "primary" ? "메인" : "서브"} 프로필로 저장됨`);
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : String(cause);
      if (!/already exists|이미 존재|교체/i.test(message)) {
        setCaptureHint(`저장 실패: ${message}`);
        return;
      }
      if (!window.confirm("기존 프로필을 교체할까요?")) return;
      try {
        await captureCodexAuthRun(run.id, slot, true);
        setCaptureHint(`${slot === "primary" ? "메인" : "서브"} 프로필 교체됨`);
      } catch (replacementCause) {
        const replacementMessage =
          replacementCause instanceof Error
            ? replacementCause.message
            : String(replacementCause);
        setCaptureHint(`교체 실패: ${replacementMessage}`);
      }
    }
  };

  return (
    <section
      className="auth-flow"
      aria-label={`${run.provider_id} CLI ${flowLabel}`}
    >
      <div className="auth-flow__head">
        <strong>
          {run.provider_id} CLI {flowLabel}
        </strong>
        <span className={`auth-flow__status auth-flow__status--${status}`}>
          {STATUS_LABELS[status]}
        </span>
      </div>
      <pre className="auth-flow__output" aria-live="polite">
        {output || `${flowLabel} 명령을 시작하는 중…`}
      </pre>
      {authUrl ? (
        <button
          type="button"
          className="btn btn--sm"
          onClick={() => void openUrl(authUrl).catch(() => undefined)}
        >
          브라우저에서 계속
        </button>
      ) : null}
      {status === "running" ? (
        <>
          <div className="auth-flow__input-row">
            <input
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") submitInput();
              }}
              placeholder="브라우저에 표시된 인증 코드를 붙여넣으세요"
              aria-label="인증 코드 입력"
            />
            <button type="button" className="btn btn--sm" onClick={submitInput}>
              입력
            </button>
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
          <p className="auth-flow__hint">
            {run.provider_id === "claude"
              ? "Claude는 브라우저 승인 후 표시되는 코드를 요청합니다. 코드를 복사해 위에 붙여넣고 Enter를 누르세요."
              : "브라우저에서 승인하면 CLI가 자동으로 완료됩니다. 코드를 요청하면 붙여넣고 Enter를 누르세요."}
          </p>
        </>
      ) : (
        <div className="auth-flow__input-row">
          {status === "completed" &&
          run.provider_id === "codex" &&
          run.action === "login" ? (
            <>
              <button
                type="button"
                className="btn btn--primary btn--sm"
                onClick={() => void capture("primary")}
              >
                {codexSlots?.hasPrimary ? "메인 교체" : "메인으로 저장"}
              </button>
              <button
                type="button"
                className="btn btn--sm"
                onClick={() => void capture("fallback")}
              >
                {codexSlots?.hasFallback ? "서브 교체" : "서브로 저장"}
              </button>
            </>
          ) : null}
          <button type="button" className="btn btn--sm" onClick={onClose}>
            닫기
          </button>
          {captureHint ? (
            <span className="settings-save-hint">{captureHint}</span>
          ) : null}
        </div>
      )}
    </section>
  );
}
