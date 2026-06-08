import {
  createContext,
  useContext,
  useEffect,
  useMemo,
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
        setSlotsState((prev) => ({ ...prev, ...patch })),
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
  const { title, meta, trailing } = next;
  useEffect(() => {
    if (!ctx) return;
    ctx.setSlots({ title, meta, trailing });
    return () => ctx.clearSlots();
  }, [ctx, title, meta, trailing]);
}
