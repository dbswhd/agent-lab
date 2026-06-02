/** Browser Notification API helper (works in Tauri webview when permission granted). */

export async function ensureDesktopNotifyPermission(): Promise<boolean> {
  if (typeof Notification === "undefined") return false;
  if (Notification.permission === "granted") return true;
  if (Notification.permission === "denied") return false;
  try {
    const result = await Notification.requestPermission();
    return result === "granted";
  } catch {
    return false;
  }
}

export function notifyDesktop(title: string, body?: string): void {
  if (typeof Notification === "undefined") return;
  if (Notification.permission !== "granted") return;
  try {
    new Notification(title, body ? { body } : undefined);
  } catch {
    /* ignore — some webviews reject Notification */
  }
}
