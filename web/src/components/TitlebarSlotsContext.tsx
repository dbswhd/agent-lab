import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

export type TitlebarSlots = {
  title?: ReactNode;
  meta?: ReactNode;
  trailing?: ReactNode;
};

type TitlebarSlotsContextValue = {
  slots: TitlebarSlots;
  setSlots: (patch: TitlebarSlots) => void;
  clearSlots: () => void;
};

const TitlebarSlotsContext = createContext<TitlebarSlotsContextValue | null>(
  null,
);

export function TitlebarSlotsProvider({ children }: { children: ReactNode }) {
  const [slots, setSlotsState] = useState<TitlebarSlots>({});
  const value = useMemo(
    () => ({
      slots,
      setSlots: (patch: TitlebarSlots) =>
        setSlotsState((prev) => {
          if (
            prev.title === patch.title &&
            prev.meta === patch.meta &&
            prev.trailing === patch.trailing
          ) {
            return prev;
          }
          return { ...prev, ...patch };
        }),
      clearSlots: () => setSlotsState({}),
    }),
    [slots],
  );
  return (
    <TitlebarSlotsContext.Provider value={value}>
      {children}
    </TitlebarSlotsContext.Provider>
  );
}

export function useTitlebarSlotsContext() {
  return useContext(TitlebarSlotsContext);
}

/** RoomChat (and similar panes) register dynamic titlebar content. */
export function useTitlebarSlots(next: TitlebarSlots) {
  const ctx = useTitlebarSlotsContext();
  // Keep ctx in a ref so we can call it from effects without it being a dep.
  // Including ctx as a dep creates a feedback cycle:
  //   setSlots → new slots → new ctx → cleanup clearSlots → new ctx → setSlots ...
  const ctxRef = useRef(ctx);
  ctxRef.current = ctx;

  const { title, meta, trailing } = next;
  useEffect(() => {
    ctxRef.current?.setSlots({ title, meta, trailing });
    return () => ctxRef.current?.clearSlots();
  }, [title, meta, trailing]);
}
