import { createContext, type ReactNode } from "react";

export type TitlebarSlots = {
  title?: ReactNode;
  meta?: ReactNode;
  trailing?: ReactNode;
};

export type TitlebarSlotsContextValue = {
  slots: TitlebarSlots;
  setSlots: (patch: TitlebarSlots) => void;
  clearSlots: () => void;
};

export const TitlebarSlotsContext =
  createContext<TitlebarSlotsContextValue | null>(null);
