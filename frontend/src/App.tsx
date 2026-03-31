import { useEffect, useState } from "react";
import FloatingBar from "@/components/FloatingBar";
import AppLayout from "@/components/AppLayout";
import { checkBackendHealth } from "@/lib/backend";
import { registerHotkeys } from "@/lib/hotkeys";
import { useNeoStore } from "@/stores/neoStore";

type WindowLabel = "main" | "floating-bar";

function App() {
  const [windowLabel, setWindowLabel] = useState<WindowLabel>("main");
  const setConnected = useNeoStore((s) => s.setConnected);

  useEffect(() => {
    async function detectWindow() {
      try {
        const { getCurrentWindow } = await import("@tauri-apps/api/window");
        const label = getCurrentWindow().label as WindowLabel;
        setWindowLabel(label);
      } catch {
        setWindowLabel("main");
      }
    }
    detectWindow();
  }, []);

  // Check backend health on mount + periodic polling
  useEffect(() => {
    checkBackendHealth().then(setConnected);
    const interval = setInterval(async () => {
      setConnected(await checkBackendHealth());
    }, 10000);
    return () => clearInterval(interval);
  }, [setConnected]);

  // Register global hotkey
  useEffect(() => {
    registerHotkeys(async () => {
      try {
        const { WebviewWindow } = await import("@tauri-apps/api/webviewWindow");
        const bar = await WebviewWindow.getByLabel("floating-bar");
        if (bar) {
          await bar.show();
          await bar.setFocus();
        }
      } catch (err) {
        console.warn("Hotkey handler error:", err);
      }
    });
  }, []);

  if (windowLabel === "floating-bar") {
    return <FloatingBar />;
  }

  return <AppLayout />;
}

export default App;
