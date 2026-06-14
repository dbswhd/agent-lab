import { isTauri } from "../theme";

/**
 * Desktop notification helper. In the Tauri app we use the native notification
 * plugin (macOS WKWebView does not support the Web Notification API, so
 * background notifications never fire through `new Notification`). In a browser
 * we fall back to the Web Notification API.
 */

export async function ensureDesktopNotifyPermission(): Promise<boolean> {
  if (isTauri()) {
    try {
      const { isPermissionGranted, requestPermission } =
        await import("@tauri-apps/plugin-notification");
      if (await isPermissionGranted()) return true;
      return (await requestPermission()) === "granted";
    } catch {
      return false;
    }
  }
  if (typeof Notification === "undefined") return false;
  if (Notification.permission === "granted") return true;
  if (Notification.permission === "denied") return false;
  try {
    return (await Notification.requestPermission()) === "granted";
  } catch {
    return false;
  }
}

export function notifyDesktop(title: string, body?: string): void {
  if (isTauri()) {
    void (async () => {
      try {
        const { isPermissionGranted, requestPermission, sendNotification } =
          await import("@tauri-apps/plugin-notification");
        let granted = await isPermissionGranted();
        if (!granted) granted = (await requestPermission()) === "granted";
        if (granted) sendNotification(body ? { title, body } : { title });
      } catch {
        /* ignore — plugin unavailable */
      }
    })();
    return;
  }
  if (typeof Notification === "undefined") return;
  if (Notification.permission !== "granted") return;
  try {
    new Notification(title, body ? { body } : undefined);
  } catch {
    /* ignore — some webviews reject Notification */
  }
}
