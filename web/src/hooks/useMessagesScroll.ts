import { useCallback, useEffect, useRef, useState } from "react";

const BOTTOM_THRESHOLD_PX = 80;

function isNearBottom(el: HTMLElement): boolean {
  return (
    el.scrollHeight - el.scrollTop - el.clientHeight <= BOTTOM_THRESHOLD_PX
  );
}
function canScroll(el: HTMLElement): boolean {
  return el.scrollHeight > el.clientHeight + 8;
}

/** Attach to the workspace-scroll container; auto-scrolls when near bottom. */
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

  useEffect(() => {
    stickRef.current = true;
    setShowJumpButton(false);
  }, [resetKey]);

  useEffect(() => {
    if (!enabled || !scrollTarget) return;
    stickRef.current = true;
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
      setShowJumpButton(!near && canScroll(el));
    };
    const onScroll = () => {
      stickRef.current = isNearBottom(el);
      update();
    };

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

/** Scroll the container to top on reset/enabled change. */
export function useScrollToTop(enabled: boolean, resetKey: unknown) {
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
