import type { WorkFocusTarget } from "../components/WorkToolPanel";

export type ComposerStackFocus = WorkFocusTarget | "inbox" | "activity";

export const COMPOSER_STACK_FOCUS_EVENT = "agent-lab:composer-stack-focus";

export function focusComposerStack(focus?: ComposerStackFocus): void {
  window.dispatchEvent(
    new CustomEvent<ComposerStackFocus | undefined>(
      COMPOSER_STACK_FOCUS_EVENT,
      { detail: focus },
    ),
  );
}

export function subscribeComposerStackFocus(
  handler: (focus: ComposerStackFocus | undefined) => void,
): () => void {
  function onEvent(event: Event) {
    handler((event as CustomEvent<ComposerStackFocus | undefined>).detail);
  }
  window.addEventListener(COMPOSER_STACK_FOCUS_EVENT, onEvent);
  return () => window.removeEventListener(COMPOSER_STACK_FOCUS_EVENT, onEvent);
}
