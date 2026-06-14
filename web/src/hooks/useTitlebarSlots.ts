import { useContext, useEffect, useRef } from "react";
import {
  TitlebarSlotsContext,
  type TitlebarSlots,
} from "../components/titlebarSlotsStore";

export function useTitlebarSlotsContext() {
  return useContext(TitlebarSlotsContext);
}

/** RoomChat (and similar panes) register dynamic titlebar content. */
export function useTitlebarSlots(next: TitlebarSlots) {
  const ctx = useTitlebarSlotsContext();
  const ctxRef = useRef(ctx);
  ctxRef.current = ctx;

  const { title, meta, trailing } = next;
  useEffect(() => {
    ctxRef.current?.setSlots({ title, meta, trailing });
    return () => ctxRef.current?.clearSlots();
  }, [title, meta, trailing]);
}
