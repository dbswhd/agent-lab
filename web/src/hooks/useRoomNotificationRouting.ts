import { useCallback, useEffect } from "react";
import { focusComposerStack } from "../utils/composerStackFocus";
import {
  notificationActionForKind,
  subscribeNotificationActions,
} from "../utils/notificationActions";
import type { AppNotification } from "../utils/notificationStore";
import type { RightPanelMode } from "../utils/workspaceTabs";
import type { WorkFocusTarget } from "../components/WorkToolPanel";

export type RoomNotificationRoutingOptions = {
  focusWorkStack: (focus: WorkFocusTarget) => void;
  setRightPanelMode: (mode: RightPanelMode) => void;
  onOpenSettings?: () => void;
};

/** Notification click routing + global action subscription — extracted from RoomChat (F9). */
export function useRoomNotificationRouting({
  focusWorkStack,
  setRightPanelMode,
  onOpenSettings,
}: RoomNotificationRoutingOptions) {
  const handleNotificationOpen = useCallback(
    (note: AppNotification) => {
      const action = notificationActionForKind(note.kind);
      if (!action) return;
      if (action.type === "composer") {
        focusComposerStack(action.focus ?? "inbox");
        return;
      }
      if (action.type === "work") {
        focusWorkStack(action.focus === "execute" ? "execute" : "plan");
        return;
      }
      if (action.type === "inspector") {
        setRightPanelMode("overview");
        return;
      }
      if (action.type === "settings") {
        onOpenSettings?.();
        return;
      }
    },
    [focusWorkStack, onOpenSettings, setRightPanelMode],
  );

  useEffect(() => {
    return subscribeNotificationActions((action) => {
      if (action.type === "composer") {
        focusComposerStack(action.focus ?? "inbox");
        return;
      }
      if (action.type === "work") {
        focusWorkStack(action.focus === "execute" ? "execute" : "plan");
        return;
      }
      if (action.type === "inspector") {
        setRightPanelMode("overview");
        return;
      }
      if (action.type === "settings") {
        onOpenSettings?.();
        return;
      }
    });
  }, [focusWorkStack, onOpenSettings, setRightPanelMode]);

  return { handleNotificationOpen };
}
