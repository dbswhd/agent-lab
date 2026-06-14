import { useCallback, useEffect, useRef } from "react";
import { useTweaksDemo } from "../context/TweaksDemoContext";
import { openCommandPalette } from "../utils/desktopShortcuts";
import { useMacNotifications } from "./MacNotificationHost";

function TweakSection({ label }: { label: string }) {
  return <div className="twk-sect">{label}</div>;
}

function TweakButton({
  label,
  onClick,
}: {
  label: string;
  onClick: () => void;
}) {
  return (
    <button type="button" className="twk-btn" onClick={onClick}>
      {label}
    </button>
  );
}

function TweakToggle({
  label,
  value,
  onChange,
}: {
  label: string;
  value: boolean;
  onChange: (on: boolean) => void;
}) {
  return (
    <div className="twk-row-h">
      <div className="twk-lbl">
        <span>{label}</span>
      </div>
      <button
        type="button"
        className="twk-toggle"
        data-on={value ? "1" : "0"}
        role="switch"
        aria-checked={value}
        aria-label={label}
        onClick={() => onChange(!value)}
      >
        <i />
      </button>
    </div>
  );
}

/** Floating Tweaks panel — overlay/banner QA controls (prototype). */
export function TweaksPanel() {
  const demo = useTweaksDemo();
  const { push } = useMacNotifications();
  const panelRef = useRef<HTMLDivElement>(null);
  const offsetRef = useRef({ x: 16, y: 16 });

  useEffect(() => {
    if (!demo.panelOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") demo.setPanelOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [demo]);

  const clamp = useCallback(() => {
    const panel = panelRef.current;
    if (!panel) return;
    const pad = 16;
    const maxRight = Math.max(pad, window.innerWidth - panel.offsetWidth - pad);
    const maxBottom = Math.max(
      pad,
      window.innerHeight - panel.offsetHeight - pad,
    );
    offsetRef.current = {
      x: Math.min(maxRight, Math.max(pad, offsetRef.current.x)),
      y: Math.min(maxBottom, Math.max(pad, offsetRef.current.y)),
    };
    panel.style.right = `${offsetRef.current.x}px`;
    panel.style.bottom = `${offsetRef.current.y}px`;
  }, []);

  useEffect(() => {
    if (!demo.panelOpen) return;
    clamp();
    window.addEventListener("resize", clamp);
    return () => window.removeEventListener("resize", clamp);
  }, [demo.panelOpen, clamp]);

  const onDragStart = (e: React.MouseEvent) => {
    const panel = panelRef.current;
    if (!panel) return;
    const r = panel.getBoundingClientRect();
    const sx = e.clientX;
    const sy = e.clientY;
    const startRight = window.innerWidth - r.right;
    const startBottom = window.innerHeight - r.bottom;
    const move = (ev: MouseEvent) => {
      offsetRef.current = {
        x: startRight - (ev.clientX - sx),
        y: startBottom - (ev.clientY - sy),
      };
      clamp();
    };
    const up = () => {
      window.removeEventListener("mousemove", move);
      window.removeEventListener("mouseup", up);
    };
    window.addEventListener("mousemove", move);
    window.addEventListener("mouseup", up);
  };

  if (!demo.panelOpen) return null;

  const execVisible =
    demo.execQueueDemo !== false && demo.execQueueDemo !== "hidden";
  const execBlocked = demo.execQueueDemo === "blocked";

  return (
    <div
      ref={panelRef}
      className="twk-panel"
      role="dialog"
      aria-label="Tweaks"
      style={{
        right: offsetRef.current.x,
        bottom: offsetRef.current.y,
      }}
    >
      <div className="twk-hd" onMouseDown={onDragStart}>
        <b>Tweaks</b>
        <button
          type="button"
          className="twk-x"
          aria-label="Tweaks 닫기"
          onMouseDown={(e) => e.stopPropagation()}
          onClick={() => demo.setPanelOpen(false)}
        >
          ✕
        </button>
      </div>
      <div className="twk-body">
        <TweakSection label="오버레이 데모" />
        <TweakButton label="⌘K Command Palette" onClick={openCommandPalette} />
        <TweakButton
          label="MacAlert (delete)"
          onClick={() => demo.setShowMacAlert(true)}
        />
        <TweakButton
          label="Permission Alert"
          onClick={() => demo.setShowPermAlert(true)}
        />
        <TweakButton
          label="토스트 알림"
          onClick={() =>
            push({
              title: "실행 완료",
              body: "Oracle 검증 통과 · 3 태스크 완료",
            })
          }
        />

        <TweakSection label="배너 토글" />
        <TweakButton
          label={
            execVisible ? "ExecuteQueueBar 숨기기" : "ExecuteQueueBar 표시"
          }
          onClick={demo.toggleExecQueueVisible}
        />
        <TweakButton
          label={execBlocked ? "차단 해제" : "승인 차단 시뮬레이트"}
          onClick={() => {
            if (
              demo.execQueueDemo === false ||
              demo.execQueueDemo === "hidden"
            ) {
              demo.setExecQueueDemo("blocked");
            } else {
              demo.toggleExecBlocked();
            }
          }}
        />
        <TweakButton
          label={
            demo.consensusGateDemo
              ? "ConsensusGate 숨기기"
              : "ConsensusGate 표시"
          }
          onClick={demo.toggleConsensusGateDemo}
        />
        <TweakButton
          label={demo.objectionDemo ? "이의 해제" : "이의 시뮬레이트"}
          onClick={demo.toggleObjectionDemo}
        />
        <TweakButton
          label={demo.preflightDemo ? "Preflight 해제" : "Preflight 에러"}
          onClick={demo.togglePreflightDemo}
        />
        <TweakButton
          label={demo.planStaleDemo ? "Work plan 알림 해제" : "Work plan 알림"}
          onClick={demo.togglePlanStaleDemo}
        />
        <TweakToggle
          label="스크롤 버튼"
          value={demo.forceScrollButton}
          onChange={demo.setForceScrollButton}
        />
      </div>
    </div>
  );
}
