import { useCallback, useEffect, useState } from "react";
import {
  getLocale,
  setLocale as persistLocale,
  LOCALE_CHANGE_EVENT,
  type Locale,
} from "./locale";
import { messages, t as translate, type MessageKey } from "./messages";

export function useLocale() {
  const [locale, setLocaleState] = useState<Locale>(() => getLocale());

  useEffect(() => {
    function onChange(event: Event) {
      const next = (event as CustomEvent<Locale>).detail;
      if (next === "en" || next === "ko") setLocaleState(next);
    }
    window.addEventListener(LOCALE_CHANGE_EVENT, onChange);
    return () => window.removeEventListener(LOCALE_CHANGE_EVENT, onChange);
  }, []);

  const setLocale = useCallback((next: Locale) => {
    persistLocale(next);
    setLocaleState(next);
  }, []);

  const t = useCallback(
    (key: MessageKey) => translate(locale, key),
    [locale],
  );

  return { locale, setLocale, t, msg: messages(locale) };
}
