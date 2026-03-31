/**
 * Global hotkey registration via Tauri plugin.
 * Ctrl+Shift+N toggles the floating command bar.
 */

let _registered = false;

/** Register the global Ctrl+Shift+N shortcut. */
export async function registerHotkeys(onToggleBar: () => void) {
  if (_registered) return;

  try {
    const { register } = await import("@tauri-apps/plugin-global-shortcut");
    await register("CommandOrControl+Shift+N", (event) => {
      if (event.state === "Pressed") {
        onToggleBar();
      }
    });
    _registered = true;
  } catch (err) {
    console.warn("Failed to register global shortcut:", err);
  }
}

/** Unregister all global shortcuts. */
export async function unregisterHotkeys() {
  if (!_registered) return;

  try {
    const { unregister } = await import("@tauri-apps/plugin-global-shortcut");
    await unregister("CommandOrControl+Shift+N");
    _registered = false;
  } catch (err) {
    console.warn("Failed to unregister global shortcut:", err);
  }
}
