import {
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";

const BOTTOM_THRESHOLD_PX = 80;

function isNearBottom(el: HTMLElement): boolean {
  return el.scrollHeight - el.scrollTop - el.clientHeight <= BOTTOM_THRESHOLD_PX;
}
function canScroll(el: HTMLElement): boolean {
  return el.scrollHeight > el.clientHeight + 8;
}

/** useMessagesScroll — attach to the workspace-scroll container.
 *  Returns scrollRef (attach to the div), showJumpButton, scrollToBottom.
 *  Auto-scrolls on new messages when user is near bottom.
 */
export function useMessagesScroll(
  scrollDeps: unknown[],
  enabled = true,
  resetKey?: unknown,
) {
  const scrollElRef = useRef<HTMLDivElement | null>(null);
  const [scrollTarget, setScrollTarget] = useState<HTMLDivElement | null>(null);
  const stickRef = useRef(true);
  const [showJumpButton, setShowJumpButton] = useState(false);

  const scrollRef = useCallback((node: HTMLDivElement | null) => {
    scrollElRef.current = node;
    setScrollTarget(node);
  }, []);

  /* Reset on session change */
  useEffect(() => {
    stickRef.current = true;
    setShowJumpButton(false);
  }, [resetKey]);

  /* Scroll to bottom on mount / reset */
  useEffect(() => {
    if (!enabled || !scrollTarget) return;
    stickRef.current = true;
    setShowJumpButton(false);
    scrollTarget.scrollTo({ top: scrollTarget.scrollHeight, behavior: "auto" });
  }, [scrollTarget, enabled, resetKey]);

  /* Track scroll position */
  useEffect(() => {
    if (!enabled || !scrollTarget) { setShowJumpButton(false); return; }
    const el = scrollTarget;

    const update = () => {
      const near = isNearBottom(el);
      setShowJumpButton(!near && canScroll(el));
    };
    const onScroll = () => { stickRef.current = isNearBottom(el); update(); };

    update();
    el.addEventListener("scroll", onScroll, { passive: true });
    const ro = new ResizeObserver(() => requestAnimationFrame(update));
    ro.observe(el);
    const mo = new MutationObserver(() => requestAnimationFrame(update));
    mo.observe(el, { childList: true });

    return () => {
      el.removeEventListener("scroll", onScroll);
      ro.disconnect();
      mo.disconnect();
    };
  }, [scrollTarget, enabled, resetKey]);

  /* Stick to bottom when new messages arrive */
  // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional dep array
  useEffect(() => {
    if (!enabled) return;
    const el = scrollElRef.current;
    if (!el || !stickRef.current) return;
    el.scrollTo({ top: el.scrollHeight, behavior: "auto" });
  }, scrollDeps);

  const scrollToBottom = useCallback(() => {
    const el = scrollElRef.current;
    if (!el) return;
    stickRef.current = true;
    setShowJumpButton(false);
    el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }, []);

  return { scrollRef, scrollElRef, showJumpButton, scrollToBottom };
}

/** useScrollToTop — scroll the container to top on reset/enabled change.
 *  Restored export — used by WorkPanel and PlanExecutePanel.
 */
export function useScrollToTop(
  enabled: boolean,
  resetKey: unknown,
) {
  const scrollElRef = useRef<HTMLDivElement | null>(null);
  const [scrollTarget, setScrollTarget] = useState<HTMLDivElement | null>(null);

  const scrollRef = useCallback((node: HTMLDivElement | null) => {
    scrollElRef.current = node;
    setScrollTarget(node);
  }, []);

  useEffect(() => {
    if (!enabled) return;
    const el = scrollElRef.current;
    if (!el) return;
    el.scrollTo({ top: 0, behavior: "auto" });
  }, [enabled, resetKey, scrollTarget]);

  return { scrollRef, scrollElRef };
}

type ButtonProps = {
  visible: boolean;
  onClick: () => void;
};

/** ScrollToBottomButton — floating ↓ button shown when scrolled up.
 *
 *  Uses .scroll-to-bottom-btn / .is-visible (overlays.css).
 *  Position: absolute bottom-right inside a position:relative scroll container.
 */
export function ScrollToBottomButton({ visible, onClick }: ButtonProps) {
  return (
    <button
      type="button"
      className={`scroll-to-bottom-btn${visible ? " is-visible" : ""}`}
      onClick={onClick}
      aria-label="맨 아래로"
      title="맨 아래로"
      aria-hidden={!visible}
      tabIndex={visible ? 0 : -1}
    >
      <svg
        className="scroll-to-bottom-btn__icon"
        viewBox="0 0 16 16"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.75"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        <path d="M8 3.5v9" />
        <path d="m4.5 9 3.5 3.5L11.5 9" />
      </svg>
    </button>
  );
}
