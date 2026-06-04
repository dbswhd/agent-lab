export type ContentTab = "chat" | "plan";

export const CONTENT_TAB_SHORTCUT_EVENT = "agent-lab:content-tab-shortcut";

export function requestContentTab(tab: ContentTab): void {
  window.dispatchEvent(
    new CustomEvent<ContentTab>(CONTENT_TAB_SHORTCUT_EVENT, { detail: tab }),
  );
}
