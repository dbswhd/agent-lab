import { useEffect, useRef, type RefObject } from "react";

/**
 * Calls `onDismiss` on pointerdown outside the boundary ref.
 * Optional `insideRef` marks an extra region (e.g. composer capsule) as inside.
 */
export function useDismissOnPointerDownOutside(
  active: boolean,
  onDismiss: () => void,
  boundaryRef?: RefObject<Node | null>,
  insideRef?: RefObject<Node | null>,
  extraBoundaryRefs?: RefObject<Node | null>[],
): RefObject<HTMLDivElement> {
  const localRef = useRef<HTMLDivElement>(null);
  const onDismissRef = useRef(onDismiss);
  onDismissRef.current = onDismiss;
  const boundaryRefRef = useRef(boundaryRef);
  boundaryRefRef.current = boundaryRef ?? localRef;
  const insideRefRef = useRef(insideRef);
  insideRefRef.current = insideRef;
  const extraBoundaryRefsRef = useRef(extraBoundaryRefs);
  extraBoundaryRefsRef.current = extraBoundaryRefs;

  useEffect(() => {
    if (!active) return;
    function onPointerDown(event: PointerEvent) {
      const target = event.target;
      if (!(target instanceof Node)) return;
      if (boundaryRefRef.current?.current?.contains(target)) return;
      if (insideRefRef.current?.current?.contains(target)) return;
      for (const ref of extraBoundaryRefsRef.current ?? []) {
        if (ref?.current?.contains(target)) return;
      }
      onDismissRef.current();
    }
    window.addEventListener("pointerdown", onPointerDown);
    return () => window.removeEventListener("pointerdown", onPointerDown);
  }, [active]);

  return localRef;
}
