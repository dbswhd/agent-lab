import { useMemo, useState, type ReactNode } from "react";
import { TitlebarSlotsContext, type TitlebarSlots } from "./titlebarSlotsStore";

export type { TitlebarSlots } from "./titlebarSlotsStore";

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
