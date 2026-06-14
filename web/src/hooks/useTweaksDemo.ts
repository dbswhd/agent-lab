import { useContext } from "react";
import {
  TweaksDemoContext,
  type TweaksDemoContextValue,
} from "../context/tweaksDemoStore";

export function useTweaksDemo(): TweaksDemoContextValue {
  const ctx = useContext(TweaksDemoContext);
  if (!ctx) {
    throw new Error("useTweaksDemo must be used inside TweaksDemoProvider");
  }
  return ctx;
}

export function useTweaksDemoOptional(): TweaksDemoContextValue | null {
  return useContext(TweaksDemoContext);
}
