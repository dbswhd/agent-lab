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

export function useMessagesScroll(
  scrollDeps: unknown[],
  enabled = true,
  resetKey?: unknown,
) {
  const scrollElRef = useRef<HTMLDivElement | null>(null);
  const [scrollTarget, setScrollTarget] = useState<HTMLDivElement | null>(null);
  /** When true, new messages auto-scroll to bottom. Cleared when user scrolls up. */
  const stickToBottomRef = useRef(true);
  const [showJumpButton, setShowJumpButton] = useState(false);

  const scrollRef = useCallback((node: HTMLDivElement | null) => {
    scrollElRef.current = node;
    setScrollTarget(node);
  }, []);

  useEffect(() => {
    stickToBottomRef.current = true;
    setShowJumpButton(false);
  }, [resetKey]);

  useEffect(() => {
    if (!enabled || !scrollTarget) return;
    stickToBottomRef.current = true;
    setShowJumpButton(false);
    scrollTarget.scrollTo({ top: scrollTarget.scrollHeight, behavior: "auto" });
  }, [scrollTarget, enabled, resetKey]);

  useEffect(() => {
    if (!enabled || !scrollTarget) {
      setShowJumpButton(false);
      return;
    }

    const el = scrollTarget;

    const update = () => {
      const near = isNearBottom(el);
      const scrollable = canScroll(el);
      setShowJumpButton(!near && scrollable);
    };

    const onScroll = () => {
      stickToBottomRef.current = isNearBottom(el);
      update();
    };

    update();
    el.addEventListener("scroll", onScroll, { passive: true });

    const ro = new ResizeObserver(() => {
      requestAnimationFrame(update);
    });
    ro.observe(el);

    const mo = new MutationObserver(() => {
      requestAnimationFrame(update);
    });
    mo.observe(el, { childList: true });

    return () => {
      el.removeEventListener("scroll", onScroll);
      ro.disconnect();
      mo.disconnect();
    };
  }, [scrollTarget, enabled, resetKey]);

  useEffect(() => {
    if (!enabled) return;
    const el = scrollElRef.current;
    if (!el || !stickToBottomRef.current) return;
    el.scrollTo({ top: el.scrollHeight, behavior: "auto" });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- scroll when chat content changes
  }, scrollDeps);

  const scrollToBottom = useCallback(() => {
    const el = scrollElRef.current;
    if (!el) return;
    stickToBottomRef.current = true;
    setShowJumpButton(false);
    el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }, []);

  return { scrollRef, scrollElRef, showJumpButton, scrollToBottom };
}

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
        aria-hidden
      >
        <path d="M8 3.5v9" />
        <path d="m4.5 9 3.5 3.5L11.5 9" />
      </svg>
    </button>
  );
}
