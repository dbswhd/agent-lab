export type Locale = "en" | "ko";

const STORAGE_KEY = "agent-lab-locale";

export const LOCALE_CHANGE_EVENT = "agent-lab-locale-change";

export function getLocale(): Locale {
  const stored = localStorage.getItem(STORAGE_KEY);
  return stored === "ko" ? "ko" : "en";
}

export function setLocale(locale: Locale): void {
  localStorage.setItem(STORAGE_KEY, locale);
  document.documentElement.lang = locale;
  window.dispatchEvent(
    new CustomEvent(LOCALE_CHANGE_EVENT, { detail: locale }),
  );
}

export function localeLabel(locale: Locale): string {
  return locale === "ko" ? "한국어" : "English";
}
