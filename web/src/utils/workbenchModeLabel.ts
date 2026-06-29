import type { RightPanelMode } from "./workspaceTabs";
import type { Locale } from "../i18n/locale";
import { messages } from "../i18n/messages";

export function workbenchModeLabel(
  mode: RightPanelMode,
  locale: Locale,
): string {
  const msg = messages(locale);
  switch (mode) {
    case "overview":
      return msg.ctxOverview;
    case "preview":
      return msg.preview;
    case "files":
      return msg.files;
    case "terminal":
      return msg.terminal;
    case "diff":
      return msg.diff;
    case "background":
      return msg.background;
  }
}
