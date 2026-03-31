/**
 * Desktop notification helpers via Tauri plugin.
 */

/** Send a desktop notification. */
export async function notify(title: string, body: string): Promise<void> {
  try {
    const { isPermissionGranted, requestPermission, sendNotification } =
      await import("@tauri-apps/plugin-notification");

    let granted = await isPermissionGranted();
    if (!granted) {
      const result = await requestPermission();
      granted = result === "granted";
    }
    if (granted) {
      sendNotification({ title, body });
    }
  } catch (err) {
    console.warn("Notification not available:", err);
  }
}

/** Notify on task completion (convenience wrapper). */
export async function notifyTaskComplete(message: string): Promise<void> {
  await notify("Neo — Task Complete", message);
}
